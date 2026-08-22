"""
Kindle Dashboard Renderer v2 — Modern Design (800×600 grayscale)

Clean rounded aesthetic optimised for Kindle e-ink display.
Layout: three-line header, two-column body with
calendar/tasks (left 55 %) and forecast/containers (right 45 %).
"""

import os
import io
import logging
import requests
from typing import Optional
from datetime import datetime, timedelta, date
from collections import OrderedDict
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from weather_icons import draw_weather_icon, WMO_DESCRIPTIONS

logger = logging.getLogger(__name__)

# ── Layout constants ──────────────────────────────────────────────────
DEFAULT_WIDTH = 800
DEFAULT_HEIGHT = 600
MARGIN = 10
HEADER_H = 100
CARD_R = 6            # corner radius for rounded cards

CZECH_MONTHS = [
    'ledna', 'února', 'března', 'dubna', 'května', 'června',
    'července', 'srpna', 'září', 'října', 'listopadu', 'prosince',
]
CZECH_DAYS = [
    'Pondělí', 'Úterý', 'Středa', 'Čtvrtek',
    'Pátek', 'Sobota', 'Neděle',
]


# ── Timezone ──────────────────────────────────────────────────────────

def _get_now() -> datetime:
    tz_name = os.environ.get("TZ", "Europe/Prague")
    try:
        return datetime.now(ZoneInfo(tz_name))
    except Exception:
        return datetime.now()


# ── Font loading ──────────────────────────────────────────────────────

def _load_font(bold=False, size=16):
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
        'clock':        _load_font(bold=True,  size=56),
        'date':         _load_font(bold=False, size=16),
        'section':      _load_font(bold=True,  size=13),
        'day_label':    _load_font(bold=True,  size=14),
        'body':         _load_font(bold=False, size=15),
        'body_bold':    _load_font(bold=True,  size=15),
        'small':        _load_font(bold=False, size=12),
        'tiny':         _load_font(bold=False, size=11),
        'weather_temp': _load_font(bold=True,  size=42),
        'weather_desc': _load_font(bold=False, size=13),
        'info_line':    _load_font(bold=False, size=12),
        'footer':       _load_font(bold=False, size=11),
    }


# ── Drawing helpers ───────────────────────────────────────────────────

def _section_label(draw, text, x, y, w, fonts):
    """Uppercase label with an extending hairline. Returns next y."""
    label = text.upper()
    draw.text((x + 4, y + 2), label, font=fonts['section'], fill=40)
    tb = draw.textbbox((x + 4, y + 2), label, font=fonts['section'])
    lx = tb[2] + 8
    ly = (tb[1] + tb[3]) // 2
    if lx < x + w - 4:
        draw.line((lx, ly, x + w - 4, ly), fill=160, width=1)
    return y + 20


def _fit_text(draw, x, y, text, max_w, bold=True,
              start_sz=14, min_sz=9, fill=0):
    """Draw text, scaling font down until it fits *max_w*."""
    for sz in range(start_sz, min_sz - 1, -1):
        f = _load_font(bold=bold, size=sz)
        tw = draw.textbbox((0, 0), text, font=f)[2]
        if tw <= max_w:
            draw.text((x, y), text, font=f, fill=fill)
            return
    f = _load_font(bold=bold, size=min_sz)
    t = text
    while len(t) > 2:
        if draw.textbbox((0, 0), t + '\u2026', font=f)[2] <= max_w:
            break
        t = t[:-1]
    draw.text((x, y), (t + '\u2026' if len(t) < len(text) else t),
              font=f, fill=fill)


def _truncate(draw, text, font, max_w):
    """Return *text* (with \u2026 if needed) that fits *max_w*."""
    if draw.textbbox((0, 0), text, font=font)[2] <= max_w:
        return text
    t = text
    while len(t) > 2:
        if draw.textbbox((0, 0), t + '\u2026', font=font)[2] <= max_w:
            return t + '\u2026'
        t = t[:-1]
    return t[:2] + '\u2026'


# ── Service-icon loading & cache ──────────────────────────────────────

_icon_cache: dict = {}


def _load_icon(name: str, size: int = 18) -> Optional[Image.Image]:
    key = (name.lower(), size)
    if key in _icon_cache:
        return _icon_cache[key]

    clean = name.lower().strip()
    aliases = {
        'immich_server': 'immich',
        'seadrive': 'seafile',
        'pihole': 'pi-hole',
        'pi-hole': 'pi-hole',
    }
    cdn = aliases.get(clean, clean)

    base = os.path.dirname(os.path.abspath(__file__))
    for fn in (clean, cdn):
        for d in (os.path.join(base, 'icons'), '/app/icons'):
            p = os.path.join(d, f"{fn}.png")
            if os.path.exists(p):
                try:
                    img = Image.open(p).convert('L')
                    img = img.resize((size, size), Image.Resampling.LANCZOS)
                    _icon_cache[key] = img
                    return img
                except Exception:
                    pass

    urls: list[str] = []
    if clean in ('jangraffe.cz', 'jangraffe'):
        urls.append('https://jangraffe.cz/favicon.png')
    elif clean in ('skautitvarozna', 'skautitvarozna.cz'):
        urls.append('https://www.skautitvarozna.cz/favicon.ico')
    urls.append(
        f"https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png/{cdn}.png"
    )
    for url in urls:
        try:
            r = requests.get(url, timeout=4,
                             headers={'User-Agent': 'Mozilla/5.0'})
            if r.status_code == 200:
                raw = Image.open(io.BytesIO(r.content)).convert('RGBA')
                bg = Image.new('RGBA', raw.size, (255, 255, 255, 255))
                comp = Image.alpha_composite(bg, raw).convert('L')
                icons_dir = os.path.join(base, 'icons')
                os.makedirs(icons_dir, exist_ok=True)
                comp.save(os.path.join(icons_dir, f"{clean}.png"))
                res = comp.resize((size, size), Image.Resampling.LANCZOS)
                _icon_cache[key] = res
                return res
        except Exception:
            pass

    _icon_cache[key] = None
    return None


def _paste_icon(draw, img, x, y, sz, name, fonts):
    """Paste service icon or draw a letter fallback in a rounded box."""
    icon = _load_icon(name, sz)
    if icon:
        img.paste(icon, (x, y))
    else:
        draw.rounded_rectangle((x, y, x + sz, y + sz), radius=3,
                               outline=140, width=1)
        ch = name[0].upper() if name else '?'
        f = _load_font(bold=True, size=max(sz - 6, 8))
        tb = draw.textbbox((0, 0), ch, font=f)
        draw.text(
            (x + (sz - tb[2]) // 2, y + (sz - tb[3]) // 2 - 1),
            ch, font=f, fill=80,
        )


# ── Header (3 lines) ─────────────────────────────────────────────────

def _draw_header(draw, weather, cpu_temp, width, fonts):
    now = _get_now()
    cur = weather.get('current', {}) if weather else {}

    # Line 1 — clock (left), temperature + icon (right)
    draw.text((MARGIN + 2, 2), now.strftime("%H:%M"),
              font=fonts['clock'], fill=0)

    if cur:
        temp = cur.get('temperature', 0)
        code = cur.get('weather_code', 0)
        temp_s = (f"{temp:.0f}\u00b0C"
                  if isinstance(temp, (int, float)) else str(temp))
        tw = draw.textbbox((0, 0), temp_s, font=fonts['weather_temp'])[2]
        tx = width - MARGIN - tw
        draw.text((tx, 6), temp_s, font=fonts['weather_temp'], fill=0)
        draw_weather_icon(draw, code, tx - 56, 4, 50)

    # Line 2 — date (left), description + pressure (right)
    day = CZECH_DAYS[now.weekday()]
    mon = CZECH_MONTHS[now.month - 1]
    draw.text((MARGIN + 4, 62),
              f"{day}  {now.day}. {mon} {now.year}",
              font=fonts['date'], fill=40)

    if cur:
        desc = WMO_DESCRIPTIONS.get(cur.get('weather_code', 0), '')
        pressure = cur.get('pressure', '')
        parts = [desc]
        if pressure and pressure != 'N/A':
            try:
                parts.append(f"{int(float(pressure))} hPa")
            except (ValueError, TypeError):
                pass
        line2 = '  \u00b7  '.join(p for p in parts if p)
        if line2:
            dw = draw.textbbox((0, 0), line2,
                               font=fonts['weather_desc'])[2]
            draw.text((width - MARGIN - dw, 64), line2,
                      font=fonts['weather_desc'], fill=80)

    # Line 3 — sunrise / sunset + CPU (right-aligned)
    bits: list[str] = []
    if cur:
        sr = cur.get('sunrise', '')
        ss = cur.get('sunset', '')
        if sr:
            bits.append(f"\u2191 {sr}")
        if ss:
            bits.append(f"\u2193 {ss}")
    if cpu_temp is not None:
        bits.append(f"CPU {cpu_temp:.0f}\u00b0C")
    if bits:
        info = '    '.join(bits)
        iw = draw.textbbox((0, 0), info, font=fonts['info_line'])[2]
        draw.text((width - MARGIN - iw, 84), info,
                  font=fonts['info_line'], fill=100)

    # separator
    draw.line((MARGIN, HEADER_H, width - MARGIN, HEADER_H),
              fill=0, width=2)


# ── Calendar (grouped by day) ────────────────────────────────────────

def _group_events(events):
    today = _get_now().date()
    buckets: dict[date, list] = OrderedDict()

    for ev in events:
        s = ev.get('start')
        e = ev.get('end')
        if s is None:
            continue
        sd = s.date() if isinstance(s, datetime) else s
        if e is None:
            ed = sd
        elif isinstance(e, datetime):
            ed = ((e - timedelta(days=1)).date()
                  if e.time() == datetime.min.time() and e > s
                  else e.date())
        else:
            ed = e - timedelta(days=1) if e > sd else sd

        d = sd
        while d <= ed:
            if d >= today:
                buckets.setdefault(d, []).append(ev)
            d += timedelta(days=1)

    out: OrderedDict[str, list] = OrderedDict()
    for d in sorted(buckets):
        delta = (d - today).days
        if delta == 0:
            lbl = "Dnes"
        elif delta == 1:
            lbl = "Zítra"
        else:
            lbl = f"{CZECH_DAYS[d.weekday()]}  {d.day}.{d.month}."
        out[lbl] = buckets[d]
    return out


def _draw_calendar(draw, events, x, y0, w, y_end, fonts):
    y = _section_label(draw, "Kalendář", x, y0, w, fonts)
    if not events:
        draw.text((x + 8, y + 4),
                  "Žádné nadcházející události",
                  font=fonts['small'], fill=140)
        return

    ROW = 20
    for label, evts in _group_events(events).items():
        if y + ROW > y_end:
            break
        # day label with subtle underline
        draw.text((x + 6, y), label, font=fonts['day_label'], fill=0)
        tb = draw.textbbox((x + 6, y), label, font=fonts['day_label'])
        draw.line((x + 6, tb[3] + 1,
                   x + 6 + min(90, tb[2] - x), tb[3] + 1),
                  fill=160, width=1)
        y += ROW + 2

        for ev in evts:
            if y + ROW > y_end:
                break
            s = ev.get('start')
            if ev.get('all_day'):
                ts = 'celodenní'
            elif isinstance(s, datetime):
                ts = s.strftime('%H:%M')
            else:
                ts = ''
            summ = ev.get('summary', '')
            line = f"  {ts:<10}{summ}"
            line = _truncate(draw, line, fonts['body'], w - 16)
            draw.text((x + 6, y), line, font=fonts['body'], fill=0)
            y += ROW
        y += 4  # gap between day groups


# ── Tasks ─────────────────────────────────────────────────────────────

def _format_due(due, now):
    """Compact Czech due-label, e.g. 'Dnes 14:00', 'Zítra', '23.8.'."""
    if due is None:
        return ''
    today = now.date()

    if isinstance(due, datetime):
        # normalise timezone
        if due.tzinfo is not None and now.tzinfo is not None:
            due = due.astimezone(now.tzinfo)
        elif due.tzinfo is not None:
            due = due.replace(tzinfo=None)
        dd = due.date()
        time_s = due.strftime('%H:%M') if (due.hour or due.minute) else ''
    elif isinstance(due, date):
        dd = due
        time_s = ''
    else:
        return ''

    delta = (dd - today).days
    if delta < 0:
        day_s = 'Zpožděno'
    elif delta == 0:
        day_s = 'Dnes'
    elif delta == 1:
        day_s = 'Zítra'
    else:
        day_s = f'{dd.day}.{dd.month}.'

    return f'{day_s} {time_s}'.strip()


def _is_overdue(due, now):
    """True if *due* is in the past relative to *now*."""
    try:
        if isinstance(due, datetime):
            if due.tzinfo and now.tzinfo:
                return due.astimezone(now.tzinfo) < now
            return due.replace(tzinfo=None) < now.replace(tzinfo=None)
        if isinstance(due, date):
            return due < now.date()
    except Exception:
        pass
    return False


def _draw_tasks(draw, tasks, x, y0, w, y_end, fonts):
    y = _section_label(draw, "Úkoly", x, y0, w, fonts)
    if not tasks:
        draw.text((x + 8, y + 4), "Žádné úkoly",
                  font=fonts['small'], fill=140)
        return

    now = _get_now()
    ROW = 21
    CB = 10          # checkbox size

    for t in tasks:
        if y + ROW > y_end:
            break

        summ = t.get('summary', '')
        due = t.get('due')
        due_s = _format_due(due, now)

        # rounded checkbox
        cy = y + (ROW - CB) // 2
        draw.rounded_rectangle(
            (x + 6, cy, x + 6 + CB, cy + CB),
            radius=2, outline=0, width=1,
        )

        # due label (right-aligned, smaller font)
        dw = 0
        if due_s:
            overdue = _is_overdue(due, now)
            df = fonts['small']
            dfill = 0 if overdue else 110
            dtb = draw.textbbox((0, 0), due_s, font=df)
            dw = dtb[2] - dtb[0] + 6
            draw.text((x + w - dw, y + 4), due_s, font=df, fill=dfill)

        # task name
        max_nw = w - 26 - dw - 4
        name = _truncate(draw, summ, fonts['body'], max_nw)
        draw.text((x + 22, y + 1), name, font=fonts['body'], fill=0)

        y += ROW


# ── Forecast (rounded cards) ─────────────────────────────────────────

def _draw_forecast(draw, weather, x, y0, w, y_end, fonts):
    y = _section_label(draw, "Předpověď", x, y0, w, fonts)
    daily = weather.get('daily', []) if weather else []
    if not daily:
        draw.text((x + 8, y + 4), "Nedostupné",
                  font=fonts['small'], fill=140)
        return

    CH = 44
    GAP = 4
    for d in daily[:3]:
        if y + CH > y_end:
            break
        # rounded card
        draw.rounded_rectangle((x, y, x + w, y + CH),
                               radius=CARD_R, outline=180, width=1)

        dn = d.get('day_name', '')
        code = d.get('weather_code', 0)
        tmin = d.get('temp_min', 0)
        tmax = d.get('temp_max', 0)
        desc = (WMO_DESCRIPTIONS.get(code, '')
                if isinstance(code, int) else '')

        draw.text((x + 8, y + 5), dn,
                  font=fonts['body_bold'], fill=0)
        draw_weather_icon(draw, code, x + 38, y + 5, 24)
        draw.text((x + 68, y + 5),
                  f"{tmin:.0f}\u00b0 / {tmax:.0f}\u00b0",
                  font=fonts['body'], fill=0)
        draw.text((x + 68, y + 25), desc,
                  font=fonts['small'], fill=100)
        y += CH + GAP


# ── Containers (3-column rounded grid) ───────────────────────────────

def _draw_containers(draw, img, containers, x, y0, w, y_end, fonts):
    y = _section_label(draw, "Kontejnery", x, y0, w, fonts)
    if not containers:
        draw.text((x + 8, y + 4), "Žádné kontejnery",
                  font=fonts['small'], fill=140)
        return

    COLS = 3
    GX, GY = 5, 5
    cw = (w - (COLS - 1) * GX) // COLS
    CH = 50
    ICON = 18
    col, ry = 0, y

    for c in containers:
        if ry + CH > y_end:
            break
        cx = x + col * (cw + GX)
        name = c.get('name', '?')
        status = c.get('status', '')
        health = c.get('health', '')
        ver = c.get('version', '')

        # rounded card
        draw.rounded_rectangle(
            (cx, ry, cx + cw, ry + CH),
            radius=CARD_R, outline=160, width=1,
        )

        # service icon (centred vertically)
        iy = ry + (CH - ICON) // 2
        _paste_icon(draw, img, cx + 4, iy, ICON, name, fonts)

        # status dot (top-right corner)
        dx = cx + cw - 9
        dy = ry + 8
        dr = 3
        if status in ('running', 'active') and health == 'healthy':
            draw.ellipse((dx - dr, dy - dr, dx + dr, dy + dr), fill=0)
        elif status in ('running', 'active'):
            draw.ellipse((dx - dr, dy - dr, dx + dr, dy + dr),
                         outline=0, width=1)
        else:
            draw.line((dx - 3, dy - 3, dx + 3, dy + 3), fill=0, width=1)
            draw.line((dx + 3, dy - 3, dx - 3, dy + 3), fill=0, width=1)

        # name + version text
        tx = cx + 4 + ICON + 4
        max_tw = cw - ICON - 20

        v = ver
        if v and v.lower() in ('latest', 'release', 'stable',
                                'master', 'main'):
            v = ''
        if v and v[0].isdigit():
            v = f'v{v}'

        if v:
            _fit_text(draw, tx, ry + 5, name, max_tw,
                      bold=True, start_sz=12, min_sz=9, fill=0)
            _fit_text(draw, tx, ry + 23, v, max_tw,
                      bold=False, start_sz=10, min_sz=8, fill=100)
        else:
            _fit_text(draw, tx, ry + (CH - 12) // 2, name, max_tw,
                      bold=True, start_sz=12, min_sz=9, fill=0)

        col += 1
        if col >= COLS:
            col = 0
            ry += CH + GY


# ── E-ink optimisation ────────────────────────────────────────────────

def _optimize_for_eink(img):
    """Quantise to 16 shades, sharpen text edges."""
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.1)
    enhancer = ImageEnhance.Sharpness(img)
    img = enhancer.enhance(1.5)
    import numpy as np
    arr = np.array(img, dtype=np.float32)
    arr = np.round(arr / 17.0) * 17.0
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode='L')


# ── Main entry point ──────────────────────────────────────────────────

def render_dashboard(
    weather: dict,
    containers: list[dict],
    events: list[dict],
    tasks: list[dict],
    cpu_temp: Optional[float] = None,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> bytes:
    """Render full dashboard and return PNG bytes."""
    img = Image.new('L', (width, height), 255)
    draw = ImageDraw.Draw(img)
    fonts = _get_fonts()

    # ── header ──
    _draw_header(draw, weather, cpu_temp, width, fonts)

    # ── body geometry ──
    top = HEADER_H + 4
    bot = height - 16

    left_w = int(width * 0.55)
    rx = left_w + 8
    rw = width - rx - MARGIN

    # subtle vertical divider
    draw.line((left_w + 3, top + 4, left_w + 3, bot - 4),
              fill=200, width=1)

    # left column: calendar (62 %) / tasks (38 %)
    split_l = top + int((bot - top) * 0.62)
    _draw_calendar(draw, events, MARGIN, top,
                   left_w - MARGIN - 8, split_l - 4, fonts)
    draw.line((MARGIN + 4, split_l, left_w - 8, split_l),
              fill=200, width=1)
    _draw_tasks(draw, tasks, MARGIN, split_l + 4,
                left_w - MARGIN - 8, bot, fonts)

    # right column: forecast (35 %) / containers (65 %)
    split_r = top + int((bot - top) * 0.35)
    _draw_forecast(draw, weather, rx, top, rw, split_r - 4, fonts)
    draw.line((rx + 4, split_r, width - MARGIN - 4, split_r),
              fill=200, width=1)
    _draw_containers(draw, img, containers, rx, split_r + 4, rw,
                     bot, fonts)

    # ── footer ──
    now = _get_now()
    ft = f"Aktualizováno: {now.strftime('%H:%M')}"
    fw = draw.textbbox((0, 0), ft, font=fonts['footer'])[2]
    draw.text((width - MARGIN - fw, height - 14), ft,
              font=fonts['footer'], fill=140)

    # ── e-ink post-processing ──
    final = _optimize_for_eink(img)

    # ── optional rotation ──
    rot = int(os.environ.get('ROTATE_DEG', '0'))
    if rot in (90, 180, 270):
        final = final.rotate(rot, expand=True)

    buf = io.BytesIO()
    final.save(buf, format='PNG')
    return buf.getvalue()
