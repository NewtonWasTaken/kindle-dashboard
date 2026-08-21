"""
Kindle Dashboard Renderer — Landscape Layout (800×600)

Generates a grayscale PNG optimized for Kindle e-ink display.
Layout: large clock + date header, calendar/tasks (left ~60%),
forecast/containers (right ~40%).
"""

import io
import logging
from datetime import datetime, timedelta
from collections import OrderedDict
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

from weather_icons import draw_weather_icon, WMO_DESCRIPTIONS

DEFAULT_WIDTH = 800
DEFAULT_HEIGHT = 600
MARGIN = 12
HEADER_HEIGHT = 92
SECTION_HEADER_H = 28
LEFT_COL_RATIO = 0.60

CZECH_MONTHS = [
    'ledna', 'února', 'března', 'dubna', 'května', 'června',
    'července', 'srpna', 'září', 'října', 'listopadu', 'prosince',
]
CZECH_DAYS = ['Pondělí', 'Úterý', 'Středa', 'Čtvrtek', 'Pátek', 'Sobota', 'Neděle']

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Font loading
# ---------------------------------------------------------------------------

def _load_font(bold=False, size=16):
    """Loads a TrueType font with broad fallback chain."""
    tag = '-Bold' if bold else ''
    tag_r = '-Regular' if not bold else '-Bold'
    paths = [
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans{tag}.ttf",
        f"/usr/share/fonts/truetype/liberation/LiberationSans{tag or '-Regular'}.ttf",
        f"/usr/share/fonts/liberation-sans-fonts/LiberationSans{tag or '-Regular'}.ttf",
        f"/usr/share/fonts/google-droid-sans-fonts/DroidSans{tag}.ttf",
        f"/usr/share/fonts/google-carlito-fonts/Carlito{tag or '-Regular'}.ttf",
        f"/usr/share/fonts/adwaita-sans-fonts/AdwaitaSans{tag_r}.ttf",
    ]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default(size)


def _get_fonts():
    return {
        'clock':        _load_font(bold=True,  size=64),
        'date':         _load_font(bold=False, size=18),
        'section':      _load_font(bold=True,  size=16),
        'day_group':    _load_font(bold=True,  size=16),
        'body':         _load_font(bold=False, size=18),
        'body_bold':    _load_font(bold=True,  size=18),
        'small':        _load_font(bold=False, size=14),
        'weather_temp': _load_font(bold=True,  size=30),
        'weather_desc': _load_font(bold=False, size=14),
        'footer':       _load_font(bold=False, size=12),
    }


# ---------------------------------------------------------------------------
# Section header helper
# ---------------------------------------------------------------------------

def _draw_section_header(draw, text, x, y, w, fonts):
    """Inverted bar (white text on black) as section header. Returns next y."""
    draw.rectangle((x, y, x + w, y + SECTION_HEADER_H), fill=0)
    draw.text((x + 8, y + 5), text.upper(), font=fonts['section'], fill=255)
    return y + SECTION_HEADER_H + 4


# ---------------------------------------------------------------------------
# Header: clock + date + compact weather
# ---------------------------------------------------------------------------

def _draw_header(draw, weather, width, fonts):
    now = datetime.now()

    # ---- large clock (left) ----
    time_str = now.strftime("%H:%M")
    draw.text((MARGIN + 2, 2), time_str, font=fonts['clock'], fill=0)

    # ---- date below clock ----
    day_name = CZECH_DAYS[now.weekday()]
    month_name = CZECH_MONTHS[now.month - 1]
    date_str = f"{day_name}  {now.day}. {month_name} {now.year}"
    draw.text((MARGIN + 4, 66), date_str, font=fonts['date'], fill=40)

    # ---- compact current weather (right side) ----
    if weather and 'current' in weather:
        cur = weather['current']
        temp = cur.get('temperature', 0)
        code = cur.get('weather_code', 0)
        desc = WMO_DESCRIPTIONS.get(code, '')
        humidity = cur.get('humidity', 0)

        # temperature
        temp_str = f"{temp:.0f}°C"
        tb = draw.textbbox((0, 0), temp_str, font=fonts['weather_temp'])
        tw = tb[2] - tb[0]
        tx = width - MARGIN - tw
        draw.text((tx, 10), temp_str, font=fonts['weather_temp'], fill=0)

        # icon left of temp
        icon_sz = 30
        draw_weather_icon(draw, code, tx - icon_sz - 6, 10, icon_sz)

        # description + humidity
        desc_line = f"{desc}  ·  vlhkost {humidity}%"
        db = draw.textbbox((0, 0), desc_line, font=fonts['weather_desc'])
        dw = db[2] - db[0]
        draw.text((width - MARGIN - dw, 42), desc_line, font=fonts['weather_desc'], fill=80)

    # ---- thick bottom line ----
    draw.line((0, HEADER_HEIGHT, width, HEADER_HEIGHT), fill=0, width=2)


# ---------------------------------------------------------------------------
# Calendar (grouped by day)
# ---------------------------------------------------------------------------

def _group_events_by_day(events):
    today = datetime.now().date()
    day_map = OrderedDict()

    for ev in events:
        start = ev.get('start')
        end = ev.get('end')
        if start is None:
            continue

        start_date = start.date() if isinstance(start, datetime) else start

        if end is None:
            end_date = start_date
        elif isinstance(end, datetime):
            if end.time() == datetime.min.time() and end > start:
                end_date = (end - timedelta(days=1)).date()
            else:
                end_date = end.date()
        else:
            if end > start_date:
                end_date = end - timedelta(days=1)
            else:
                end_date = start_date

        curr_date = start_date
        while curr_date <= end_date:
            if curr_date >= today:
                day_map.setdefault(curr_date, []).append(ev)
            curr_date += timedelta(days=1)

    groups = OrderedDict()
    for ev_date in sorted(day_map.keys()):
        delta = (ev_date - today).days
        if delta == 0:
            label = "Dnes"
        elif delta == 1:
            label = "Zítra"
        else:
            label = f"{CZECH_DAYS[ev_date.weekday()]}  {ev_date.day}.{ev_date.month}."
        groups[label] = day_map[ev_date]

    return groups


def _draw_calendar(draw, events, x, y_start, col_w, y_end, fonts):
    y = _draw_section_header(draw, "Kalendář", x, y_start, col_w, fonts)

    if not events:
        draw.text((x + 10, y + 2), "Žádné nadcházející události",
                   font=fonts['small'], fill=120)
        return

    ROW = 22
    groups = _group_events_by_day(events)

    for day_label, day_events in groups.items():
        if y + ROW > y_end:
            break
        # day label
        draw.text((x + 8, y), day_label, font=fonts['day_group'], fill=0)
        # thin underline
        lb = draw.textbbox((x + 8, y), day_label, font=fonts['day_group'])
        draw.line((x + 8, lb[3] + 1, x + 8 + 90, lb[3] + 1), fill=140, width=1)
        y += ROW + 1

        for ev in day_events:
            if y + ROW > y_end:
                break
            start = ev.get('start')
            if ev.get('all_day'):
                t_str = "Celý den"
            elif isinstance(start, datetime):
                t_str = start.strftime("%H:%M")
            else:
                t_str = ""

            summary = ev.get('summary', '')
            text = f"  {t_str:<9} {summary}"
            max_w = col_w - 24
            while draw.textbbox((0, 0), text, font=fonts['body'])[2] > max_w and len(summary) > 5:
                summary = summary[:-2]
                text = f"  {t_str:<9} {summary}…"
            draw.text((x + 8, y), text, font=fonts['body'], fill=0)
            y += ROW

        y += 4  # gap between groups


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

def _draw_tasks(draw, tasks, x, y_start, col_w, y_end, fonts):
    y = _draw_section_header(draw, "Úkoly", x, y_start, col_w, fonts)

    if not tasks:
        draw.text((x + 10, y + 2), "Žádné úkoly", font=fonts['small'], fill=120)
        return

    ROW = 24
    for task in tasks[:8]:
        if y + ROW > y_end:
            break

        # checkbox
        bsz = 12
        by = y + (ROW - bsz) // 2
        draw.rectangle((x + 8, by, x + 8 + bsz, by + bsz), outline=0, width=1)

        summary = task.get('summary', '')
        due = task.get('due')
        due_str = f"  (do {due.day}.{due.month}.)" if due else ""

        text = summary
        max_w = col_w - 48
        full = text + due_str
        while draw.textbbox((0, 0), full, font=fonts['body'])[2] > max_w and len(text) > 5:
            text = text[:-2]
            full = text + "…" + due_str
        if text != summary:
            text += "…"

        draw.text((x + 28, y + 2), text, font=fonts['body'], fill=0)
        if due_str:
            tw = draw.textbbox((0, 0), text, font=fonts['body'])[2]
            draw.text((x + 28 + tw, y + 4), due_str, font=fonts['small'], fill=100)
        y += ROW


# ---------------------------------------------------------------------------
# Weather forecast (3 days)
# ---------------------------------------------------------------------------

def _draw_forecast(draw, weather, x, y_start, col_w, y_end, fonts):
    y = _draw_section_header(draw, "Předpověď", x, y_start, col_w, fonts)

    daily = weather.get('daily', []) if weather else []
    if not daily:
        draw.text((x + 10, y + 2), "Nedostupné", font=fonts['small'], fill=120)
        return

    ROW = 48
    for day in daily[:3]:
        if y + ROW > y_end:
            break
        day_name = day.get('day_name', '')
        code = day.get('weather_code', 0)
        t_min = day.get('temp_min', 0)
        t_max = day.get('temp_max', 0)
        desc = WMO_DESCRIPTIONS.get(code, '')

        draw.text((x + 8, y + 6), f"{day_name}", font=fonts['body_bold'], fill=0)
        draw_weather_icon(draw, code, x + 42, y + 2, 28)
        draw.text((x + 76, y + 6), f"{t_min:.0f}° / {t_max:.0f}°",
                   font=fonts['body'], fill=0)
        draw.text((x + 76, y + 26), desc, font=fonts['small'], fill=80)
        y += ROW


# ---------------------------------------------------------------------------
# Containers
# ---------------------------------------------------------------------------

def _draw_containers(draw, containers, x, y_start, col_w, y_end, fonts):
    y = _draw_section_header(draw, "Kontejnery", x, y_start, col_w, fonts)

    if not containers:
        draw.text((x + 10, y + 2), "Žádné kontejnery", font=fonts['small'], fill=120)
        return

    ROW = 22
    for c in containers:
        if y + ROW > y_end:
            break
        name = c.get('name', '?')
        status = c.get('status', '')
        health = c.get('health', '')

        r = 5
        cx, cy = x + 14 + r, y + ROW // 2
        if health == 'healthy' or (status == 'running' and health != 'unhealthy'):
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=0)
        elif status == 'running':
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=120)
        else:
            draw.line((cx - r, cy - r, cx + r, cy + r), fill=0, width=2)
            draw.line((cx + r, cy - r, cx - r, cy + r), fill=0, width=2)

        draw.text((x + 30, y + 1), name, font=fonts['body'], fill=0)
        y += ROW


# ---------------------------------------------------------------------------
# E-ink optimisation
# ---------------------------------------------------------------------------

def _optimize_for_eink(img):
    """Quantise to 16 grayscale levels, sharpen text."""
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.1)
    enhancer = ImageEnhance.Sharpness(img)
    img = enhancer.enhance(1.5)

    import numpy as np
    arr = np.array(img, dtype=np.float32)
    arr = np.round(arr / 17.0) * 17.0
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode='L')


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def render_dashboard(
    weather: dict,
    containers: list[dict],
    events: list[dict],
    tasks: list[dict],
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> bytes:
    """Render the full dashboard and return PNG bytes."""
    img = Image.new('L', (width, height), 255)
    draw = ImageDraw.Draw(img)
    fonts = _get_fonts()

    # ---- header ----
    _draw_header(draw, weather, width, fonts)

    # ---- layout geometry ----
    body_top = HEADER_HEIGHT + 4
    body_bot = height - 16

    left_w = int(width * LEFT_COL_RATIO)
    right_x = left_w + 6
    right_w = width - right_x - MARGIN

    # vertical divider between columns
    draw.line((left_w + 2, body_top, left_w + 2, body_bot), fill=0, width=1)

    # ---- left column: calendar (62 %) + tasks (38 %) ----
    split_left = body_top + int((body_bot - body_top) * 0.62)

    _draw_calendar(draw, events, MARGIN, body_top, left_w - MARGIN - 6,
                   split_left - 4, fonts)
    draw.line((MARGIN, split_left, left_w - 6, split_left), fill=0, width=1)
    _draw_tasks(draw, tasks, MARGIN, split_left + 3, left_w - MARGIN - 6,
                body_bot, fonts)

    # ---- right column: forecast (42 %) + containers (58 %) ----
    split_right = body_top + int((body_bot - body_top) * 0.42)

    _draw_forecast(draw, weather, right_x, body_top, right_w,
                   split_right - 4, fonts)
    draw.line((right_x, split_right, width - MARGIN, split_right),
              fill=0, width=1)
    _draw_containers(draw, containers, right_x, split_right + 3, right_w,
                     body_bot, fonts)

    # ---- outer border ----
    draw.rectangle((0, 0, width - 1, height - 1), outline=0, width=1)

    # ---- footer ----
    now = datetime.now()
    ft = f"Aktualizováno: {now.strftime('%H:%M')}"
    fb = draw.textbbox((0, 0), ft, font=fonts['footer'])
    draw.text((width - MARGIN - fb[2], height - 14), ft,
              font=fonts['footer'], fill=100)

    # ---- e-ink post-processing ----
    final = _optimize_for_eink(img)
    buf = io.BytesIO()
    final.save(buf, format="PNG")
    return buf.getvalue()
