import os
import logging
from datetime import datetime, timedelta, date
from typing import Optional
import docker
import requests
import caldav
from icalendar import Calendar as iCalendar

logger = logging.getLogger(__name__)

def _to_naive_datetime(d) -> Optional[datetime]:
    if d is None:
        return None
    if isinstance(d, datetime):
        return d.replace(tzinfo=None)
    if isinstance(d, date):
        return datetime.combine(d, datetime.min.time())
    return None

def _to_date(d) -> Optional[date]:
    if d is None:
        return None
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    return None

def _get_container_version(c) -> str:
    try:
        tags = getattr(c.image, 'tags', []) if hasattr(c, 'image') and c.image else []
        if tags and len(tags) > 0:
            full_tag = tags[0]
            if ":" in full_tag:
                tag = full_tag.split(":")[-1]
                if tag:
                    return tag
        img_name = c.attrs.get('Config', {}).get('Image', '')
        if ":" in img_name:
            return img_name.split(":")[-1]
        elif img_name:
            return img_name
    except Exception:
        pass
    return ""

def fetch_docker_status() -> list[dict]:
    try:
        client = docker.from_env()
        watched_str = os.environ.get("WATCHED_CONTAINERS", "")
        watched = [name.strip() for name in watched_str.split(",")] if watched_str else []
        
        all_containers = client.containers.list(all=True)
        container_map = {}
        for c in all_containers:
            c_name = c.name[1:] if c.name.startswith("/") else c.name
            container_map[c_name] = c

        result = []
        if watched:
            for name in watched:
                if name in container_map:
                    c = container_map[name]
                    status = c.status
                    health = "stopped"
                    if status == "running":
                        health = c.attrs.get("State", {}).get("Health", {}).get("Status", "none")
                    version = _get_container_version(c)
                    result.append({
                        "name": name,
                        "status": status,
                        "health": health,
                        "version": version
                    })
                else:
                    result.append({
                        "name": name,
                        "status": "exited",
                        "health": "stopped",
                        "version": ""
                    })
        else:
            for c_name, c in container_map.items():
                status = c.status
                health = "stopped"
                if status == "running":
                    health = c.attrs.get("State", {}).get("Health", {}).get("Status", "none")
                version = _get_container_version(c)
                result.append({
                    "name": c_name,
                    "status": status,
                    "health": health,
                    "version": version
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

def _filter_calendars(calendars: list, env_var_name: str) -> list:
    watched_str = os.environ.get(env_var_name, "").strip()
    if not watched_str:
        return calendars
    
    allowed = [name.strip().lower() for name in watched_str.split(",") if name.strip()]
    if not allowed:
        return calendars

    filtered = []
    for cal in calendars:
        names_to_check = []
        if getattr(cal, 'name', None):
            names_to_check.append(str(cal.name).lower())
        try:
            disp_name = cal.get_display_name()
            if disp_name:
                names_to_check.append(str(disp_name).lower())
        except Exception:
            pass
        
        # Check URL path component (e.g. /user/skola/ -> skola)
        url_str = str(cal.url).rstrip('/').split('/')[-1].lower()
        names_to_check.append(url_str)
        import urllib.parse
        names_to_check.append(urllib.parse.unquote(url_str))

        if any(n in allowed for n in names_to_check):
            filtered.append(cal)
        else:
            logger.info(f"Skipping calendar {cal.url} (names {names_to_check} not in {allowed})")
            
    return filtered

def fetch_calendar_events(max_events: int = 15) -> list[dict]:
    try:
        client = _get_caldav_client()
        if not client:
            return []
        
        principal = client.principal()
        all_calendars = principal.calendars()
        calendars = _filter_calendars(all_calendars, "WATCHED_CALENDARS")
        
        now = datetime.now()
        start = now
        end = now + timedelta(days=7)
        
        events = []
        for cal in calendars:
            try:
                cal_events = cal.search(event=True, start=start, end=end)
                
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
                                dtstart_naive = _to_naive_datetime(dtstart)
                                dtend_naive = _to_naive_datetime(dtend)
                                dtend_d = _to_date(dtend)
                                
                                # Filter past events safely
                                if all_day:
                                    if dtend_d and dtend_d < now.date():
                                        continue
                                    sort_key = dtstart_naive
                                else:
                                    if dtend_naive and dtend_naive < now:
                                        continue
                                    sort_key = dtstart_naive
                                    
                                events.append({
                                    "summary": summary,
                                    "start": dtstart,
                                    "end": dtend,
                                    "all_day": all_day,
                                    "_sort_key": sort_key
                                })
                    except Exception as e:
                        logger.error(f"Error parsing VEVENT: {e}")
            except Exception as e:
                logger.error(f"Error searching calendar for events: {e}")
                
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
        all_calendars = principal.calendars()
        calendars = _filter_calendars(all_calendars, "WATCHED_TASK_CALENDARS")
        
        tasks = []
        for cal in calendars:
            try:
                # Fetch TODOs without strict XML STATUS filter so tasks lacking STATUS header are included
                todos = cal.search(todo=True)
                
                for todo in todos:
                    try:
                        cal_obj = iCalendar.from_ical(todo.data)
                        for component in cal_obj.walk():
                            if component.name == "VTODO":
                                status = str(component.get('status', 'NEEDS-ACTION')).upper()
                                percent = component.get('percent-complete')
                                
                                if status in ('COMPLETED', 'CANCELLED') or percent == 100:
                                    continue
                                    
                                summary = str(component.get('summary', ''))
                                due_prop = component.get('due') or component.get('dtstart')
                                due = due_prop.dt if due_prop else None
                                priority = int(component.get('priority', 0))
                                
                                tasks.append({
                                    "summary": summary,
                                    "due": due,
                                    "priority": priority,
                                    "status": status
                                })
                    except Exception as e:
                        logger.error(f"Error parsing VTODO: {e}")
            except Exception as e:
                logger.error(f"Error searching TODOs: {e}")
                
        # Sort tasks by due date ascending safely
        def task_sort_key(t):
            due_dt = _to_naive_datetime(t["due"])
            if due_dt is None:
                return (1, datetime.max)
            return (0, due_dt)
            
        tasks.sort(key=task_sort_key)
        return tasks
    except Exception as e:
        logger.error(f"Error fetching tasks: {e}")
        return []
