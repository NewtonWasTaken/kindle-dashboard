import os
import logging
from datetime import datetime, timedelta
from typing import Optional
import docker
import requests
import caldav
from icalendar import Calendar as iCalendar

logger = logging.getLogger(__name__)

def fetch_docker_status() -> list[dict]:
    try:
        client = docker.from_env()
        watched_str = os.environ.get("WATCHED_CONTAINERS", "")
        watched = [name.strip() for name in watched_str.split(",")] if watched_str else []
        
        containers = client.containers.list(all=True)
        result = []
        for c in containers:
            name = c.name
            if name.startswith("/"):
                name = name[1:]
            
            if watched and name not in watched:
                continue
                
            status = c.status
            health = "stopped"
            if status == "running":
                health = c.attrs.get("State", {}).get("Health", {}).get("Status", "none")
                
            result.append({
                "name": name,
                "status": status,
                "health": health
            })
        return result
    except Exception as e:
        logger.error(f"Error fetching Docker status: {e}")
        return []

def fetch_weather() -> dict:
    try:
        lat = os.environ.get("WEATHER_LAT", "49.1847")
        lon = os.environ.get("WEATHER_LON", "16.7064")
        url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
               "&current=temperature_2m,relative_humidity_2m,weather_code"
               "&daily=weather_code,temperature_2m_max,temperature_2m_min"
               "&timezone=Europe/Prague&forecast_days=4")
        
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        current = data.get("current", {})
        daily = data.get("daily", {})
        
        res = {
            "current": {
                "temperature": current.get("temperature_2m", "N/A"),
                "humidity": current.get("relative_humidity_2m", "N/A"),
                "weather_code": current.get("weather_code", "N/A"),
            },
            "daily": []
        }
        
        days_map = ["Po", "Út", "St", "Čt", "Pá", "So", "Ne"]
        
        dates = daily.get("time", [])
        codes = daily.get("weather_code", [])
        t_max = daily.get("temperature_2m_max", [])
        t_min = daily.get("temperature_2m_min", [])
        
        # Skip today (index 0), return next 3 days
        for i in range(1, min(4, len(dates))):
            d_str = dates[i]
            d_obj = datetime.strptime(d_str, "%Y-%m-%d")
            res["daily"].append({
                "date": d_str,
                "day_name": days_map[d_obj.weekday()],
                "temp_min": t_min[i] if i < len(t_min) else "N/A",
                "temp_max": t_max[i] if i < len(t_max) else "N/A",
                "weather_code": codes[i] if i < len(codes) else "N/A"
            })
        return res
    except Exception as e:
        logger.error(f"Error fetching weather: {e}")
        return {
            "current": {"temperature": "N/A", "humidity": "N/A", "weather_code": "N/A"},
            "daily": []
        }

def _get_caldav_client() -> Optional[caldav.DAVClient]:
    url = os.environ.get("RADICALE_URL")
    user = os.environ.get("RADICALE_USER")
    password = os.environ.get("RADICALE_PASS")
    if not url:
        return None
    return caldav.DAVClient(url=url, username=user, password=password, timeout=5)

def fetch_calendar_events(max_events: int = 5) -> list[dict]:
    try:
        client = _get_caldav_client()
        if not client:
            return []
        principal = client.principal()
        calendars = principal.calendars()
        
        now = datetime.now()
        start = now
        end = now + timedelta(days=7)
        
        events = []
        for calendar in calendars:
            try:
                # bulk REPORT query (fetches all event data in 1 request per calendar)
                cal_events = calendar.search(event=True, start=start, end=end)
                for event in cal_events:
                    try:
                        cal_obj = iCalendar.from_ical(event.data)
                        for component in cal_obj.walk():
                            if component.name == "VEVENT":
                                summary = str(component.get('summary', ''))
                                dtstart_prop = component.get('dtstart')
                                dtend_prop = component.get('dtend')
                                
                                if not dtstart_prop:
                                    continue
                                    
                                dtstart = dtstart_prop.dt
                                dtend = dtend_prop.dt if dtend_prop else dtstart
                                
                                all_day = not isinstance(dtstart, datetime)
                                
                                # Filter out past events
                                if all_day:
                                    if dtend < now.date():
                                        continue
                                    sort_key = datetime.combine(dtstart, datetime.min.time())
                                else:
                                    dtend_naive = dtend.replace(tzinfo=None) if hasattr(dtend, 'replace') else dtend
                                    if dtend_naive < now:
                                        continue
                                    sort_key = dtstart.replace(tzinfo=None) if hasattr(dtstart, 'replace') else dtstart
                                    
                                events.append({
                                    "summary": summary,
                                    "start": dtstart,
                                    "end": dtend,
                                    "all_day": all_day,
                                    "_sort_key": sort_key
                                })
                    except Exception as e:
                        logger.error(f"Error parsing event: {e}")
            except Exception as e:
                logger.error(f"Error searching calendar: {e}")
                
        events.sort(key=lambda x: x["_sort_key"])
        
        for e in events:
            del e["_sort_key"]
            
        return events[:max_events]
    except Exception as e:
        logger.error(f"Error fetching calendar events: {e}")
        return []

def fetch_tasks() -> list[dict]:
    try:
        client = _get_caldav_client()
        if not client:
            return []
        principal = client.principal()
        calendars = principal.calendars()
        
        tasks = []
        for calendar in calendars:
            try:
                # Bulk REPORT query: fetch ONLY uncompleted TODOs in 1 request per calendar
                todos = calendar.search(todo=True, include_completed=False)
                for todo in todos:
                    try:
                        cal_obj = iCalendar.from_ical(todo.data)
                        for component in cal_obj.walk():
                            if component.name == "VTODO":
                                status = str(component.get('status', 'NEEDS-ACTION')).upper()
                                percent = component.get('percent-complete')
                                
                                # Skip completed or cancelled tasks
                                if status == 'COMPLETED' or status == 'CANCELLED' or percent == 100:
                                    continue
                                    
                                summary = str(component.get('summary', ''))
                                due_prop = component.get('due')
                                due = due_prop.dt if due_prop else None
                                
                                priority = int(component.get('priority', 0))
                                
                                tasks.append({
                                    "summary": summary,
                                    "due": due,
                                    "priority": priority,
                                    "status": status
                                })
                    except Exception as e:
                        logger.error(f"Error parsing task: {e}")
            except Exception as e:
                pass
                
        def task_sort_key(t):
            p = t["priority"]
            p_key = (p == 0, -p)
            due = t["due"]
            if due is None:
                due_key = (1, datetime.max)
            else:
                if not isinstance(due, datetime):
                    due = datetime.combine(due, datetime.min.time())
                due_key = (0, due.replace(tzinfo=None))
            return (p_key, due_key)
            
        tasks.sort(key=task_sort_key)
        return tasks
    except Exception as e:
        logger.error(f"Error fetching tasks: {e}")
        return []
