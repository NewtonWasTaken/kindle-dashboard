"""
Kindle Dashboard Renderer — Landscape Layout (800×600)

Generates a grayscale PNG optimized for Kindle e-ink display.
Layout: large clock + date header, calendar/tasks (left ~60%),
forecast/containers (right ~40%).
"""

import os
import io
import logging
import requests
from typing import Optional
from datetime import datetime, timedelta
from collections import OrderedDict
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

def _get_now() -> datetime:
    tz_name = os.environ.get("TZ", "Europe/Prague")
    try:
        return datetime.now(ZoneInfo(tz_name))
    except Exception:
        return datetime.now()

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
        'weather_temp': _load_font(bold=True,  size=48),
        'weather_desc': _load_font(bold=False, size=15),
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
# Header: clock + date + prominent weather
# ---------------------------------------------------------------------------

def _draw_header(draw, weather, width, fonts):
    now = _get_now()

    # ---- large clock (left) ----
    time_str = now.strftime("%H:%M")
    draw.text((MARGIN + 2, 2), time_str, font=fonts['clock'], fill=0)

    # ---- date below clock ----
    day_name = CZECH_DAYS[now.weekday()]
    month_name = CZECH_MONTHS[now.month - 1]
    date_str = f"{day_name}  {now.day}. {month_name} {now.year}"
    draw.text((MARGIN + 4, 66), date_str, font=fonts['date'], fill=40)

    # ---- prominent current weather (right side) ----
    if weather and 'current' in weather:
        cur = weather['current']
        temp = cur.get('temperature', 0)
        code = cur.get('weather_code', 0)
        desc = WMO_DESCRIPTIONS.get(code, '')
        humidity = cur.get('humidity', 0)

        # temperature (48px bold)
        temp_str = f"{temp:.0f}°C" if isinstance(temp, (int, float)) else str(temp)
        tb = draw.textbbox((0, 0), temp_str, font=fonts['weather_temp'])
        tw = tb[2] - tb[0]
        tx = width - MARGIN - tw
        draw.text((tx, 8), temp_str, font=fonts['weather_temp'], fill=0)

        # weather icon (44x44)
        icon_sz = 44
        draw_weather_icon(draw, code, tx - icon_sz - 10, 8, icon_sz)

        # description + humidity (15px)
        desc_line = f"{desc}  ·  vlhkost {humidity}%"
        db = draw.textbbox((0, 0), desc_line, font=fonts['weather_desc'])
        dw = db[2] - db[0]
        draw.text((width - MARGIN - dw, 66), desc_line, font=fonts['weather_desc'], fill=80)

    # ---- thick bottom line ----
    draw.line((0, HEADER_HEIGHT, width, HEADER_HEIGHT), fill=0, width=2)


# ---------------------------------------------------------------------------
# Calendar (grouped by day)
# ---------------------------------------------------------------------------

def _group_events_by_day(events):
    today = _get_now().date()
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

def _draw_heart_icon(draw, cx, cy, size=12):
    """Draws a filled heart icon centered at (cx, cy)."""
    r = size // 4
    draw.ellipse((cx - 2*r, cy - 2*r, cx, cy), fill=0)
    draw.ellipse((cx, cy - 2*r, cx + 2*r, cy), fill=0)
    pts = [(cx - 2*r, cy - r // 2), (cx + 2*r, cy - r // 2), (cx, cy + 2*r)]
    draw.polygon(pts, fill=0)

_icon_cache = {}

def _get_service_icon_img(name: str, size: int = 20) -> Optional[Image.Image]:
    key = (name.lower(), size)
    if key in _icon_cache:
        return _icon_cache[key]

    name_clean = name.lower().strip()
    
    alias_map = {
        'immich_server': 'immich',
        'seadrive': 'seafile',
        'pihole': 'pi-hole',
        'pi-hole': 'pi-hole',
    }
    cdn_name = alias_map.get(name_clean, name_clean)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    icon_paths = [
        os.path.join(base_dir, 'icons', f"{name_clean}.png"),
        os.path.join(base_dir, 'icons', f"{cdn_name}.png"),
        f"/app/icons/{name_clean}.png",
        f"/app/icons/{cdn_name}.png",
    ]

    for p in icon_paths:
        if os.path.exists(p):
            try:
                img = Image.open(p).convert('L')
                img = img.resize((size, size), Image.Resampling.LANCZOS)
                _icon_cache[key] = img
                return img
            except Exception:
                pass

    # Try downloading from CDN or direct website favicons
    urls_to_try = []
    if name_clean in ('jangraffe.cz', 'jangraffe'):
        urls_to_try.append('https://jangraffe.cz/favicon.png')
    elif name_clean in ('skautitvarozna', 'skautitvarozna.cz'):
        urls_to_try.append('https://www.skautitvarozna.cz/favicon.ico')
    
    urls_to_try.append(f"https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/{cdn_name}.png")

    for url in urls_to_try:
        try:
            resp = requests.get(url, timeout=4, headers={'User-Agent': 'Mozilla/5.0'})
            if resp.status_code == 200:
                raw = Image.open(io.BytesIO(resp.content)).convert('RGBA')
                bg = Image.new('RGBA', raw.size, (255, 255, 255, 255))
                composite = Image.alpha_composite(bg, raw).convert('L')
                
                icons_dir = os.path.join(base_dir, 'icons')
                os.makedirs(icons_dir, exist_ok=True)
                save_p = os.path.join(icons_dir, f"{name_clean}.png")
                composite.save(save_p)
                
                res_img = composite.resize((size, size), Image.Resampling.LANCZOS)
                _icon_cache[key] = res_img
                return res_img
        except Exception:
            pass

    _icon_cache[key] = None
    return None

def _draw_service_icon(draw, target_img, x, y, size, name, fonts):
    """Draws a real service PNG icon or falls back to letter badge."""
    icon_img = _get_service_icon_img(name, size)
    if icon_img:
        target_img.paste(icon_img, (x, y))
    else:
        draw.rectangle((x, y, x + size, y + size), outline=0, width=1)
        letter = name[0].upper() if name else "?"
        tb = draw.textbbox((0, 0), letter, font=fonts['section'])
        tw = tb[2] - tb[0]
        th = tb[3] - tb[1]
        draw.text((x + (size - tw) // 2, y + (size - th) // 2 - 1), letter, font=fonts['section'], fill=0)

def _draw_autoscale_text(draw, x, y, text: str, max_w: int, bold: bool = True, start_size: int = 17, min_size: int = 9, fill: int = 0):
    """Draws text by dynamically scaling down font size so it fits inside max_w."""
    for sz in range(start_size, min_size - 1, -1):
        font = _load_font(bold=bold, size=sz)
        tb = draw.textbbox((0, 0), text, font=font)
        if (tb[2] - tb[0]) <= max_w:
            draw.text((x, y), text, font=font, fill=fill)
            return
    # Fallback to min_size with slight truncation if needed
    font = _load_font(bold=bold, size=min_size)
    t = text
    while len(t) > 2 and draw.textbbox((0, 0), t + '…', font=font)[2] > max_w:
        t = t[:-1]
    final_text = t + '…' if len(t) < len(text) else t
    draw.text((x, y), final_text, font=font, fill=fill)

def _draw_containers(draw, containers, x, y_start, col_w, y_end, fonts):
    y = _draw_section_header(draw, "Kontejnery", x, y_start, col_w, fonts)

    if not containers:
        draw.text((x + 10, y + 2), "Žádné kontejnery", font=fonts['small'], fill=120)
        return

    gap_x = 6
    card_w = (col_w - gap_x) // 2
    card_h = 41
    gap_y = 5

    col = 0
    row_y = y

    for c in containers:
        if row_y + card_h > y_end:
            break

        card_x = x + col * (card_w + gap_x)

        name = c.get('name', '?')
        status = c.get('status', '')
        health = c.get('health', '')
        version = c.get('version', '')

        # Card container box
        draw.rectangle((card_x, row_y, card_x + card_w, row_y + card_h), outline=140, width=1)

        # Service icon on left (22x22)
        icon_sz = 22
        icon_x = card_x + 5
        icon_y = row_y + (card_h - icon_sz) // 2
        _draw_service_icon(draw, draw._image, icon_x, icon_y, icon_sz, name, fonts)

        # Status icon on right (heart / dot / cross)
        stat_x = card_x + card_w - 14
        stat_y = row_y + card_h // 2

        if status in ('running', 'active') and health == 'healthy':
            # Heart for healthy
            _draw_heart_icon(draw, stat_x, stat_y, size=13)
        elif status in ('running', 'active'):
            # Dot for running (no healthcheck)
            draw.ellipse((stat_x - 4, stat_y - 4, stat_x + 4, stat_y + 4), fill=0)
        else:
            # Cross for down / exited / unhealthy
            draw.line((stat_x - 4, stat_y - 4, stat_x + 4, stat_y + 4), fill=0, width=2)
            draw.line((stat_x + 4, stat_y - 4, stat_x - 4, stat_y + 4), fill=0, width=2)

        # Name and version text in middle
        text_x = icon_x + icon_sz + 6
        max_text_w = (stat_x - 8) - text_x

        v_str = version if version else (status if status != 'running' else '')
        if v_str and v_str.lower() in ('latest', 'release', 'stable'):
            v_str = ""

        if v_str:
            if v_str[0].isdigit():
                v_str = f"v{v_str}"
            # Name at top, version below
            _draw_autoscale_text(draw, text_x, row_y + 2, name, max_text_w, bold=True, start_size=16, min_size=10, fill=0)
            _draw_autoscale_text(draw, text_x, row_y + 22, v_str, max_text_w, bold=False, start_size=12, min_size=9, fill=100)
        else:
            # No version tag -> vertically center container name in 41px card
            _draw_autoscale_text(draw, text_x, row_y + 11, name, max_text_w, bold=True, start_size=16, min_size=10, fill=0)

        col += 1
        if col >= 2:
            col = 0
            row_y += card_h + gap_y


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

    # ---- optional rotation for Kindle hardware panel ----
    rotate_deg = int(os.environ.get("ROTATE_DEG", "0"))
    if rotate_deg in (90, 180, 270):
        final = final.rotate(rotate_deg, expand=True)

    buf = io.BytesIO()
    final.save(buf, format="PNG")
    return buf.getvalue()
