import math
from PIL import Image, ImageDraw

WMO_DESCRIPTIONS: dict[int, str] = {
    0: "Jasno",
    1: "Převážně jasno",
    2: "Polojasno",
    3: "Zataženo",
    45: "Mlha", 48: "Mlha",
    51: "Mrholení", 53: "Mrholení", 55: "Mrholení",
    56: "Mrznoucí mrholení", 57: "Mrznoucí mrholení",
    61: "Déšť", 63: "Déšť", 65: "Déšť",
    66: "Mrznoucí déšť", 67: "Mrznoucí déšť",
    71: "Sněžení", 73: "Sněžení", 75: "Sněžení",
    77: "Sněhové krupky",
    80: "Přeháňky", 81: "Přeháňky", 82: "Přeháňky",
    85: "Sněhové přeháňky", 86: "Sněhové přeháňky",
    95: "Bouřka",
    96: "Bouřka s kroupami", 99: "Bouřka s kroupami",
}

def draw_weather_icon(img_or_draw, wmo_code: int, x: int, y: int, size: int):
    """
    Draws a weather icon at the given position using Pillow drawing primitives.
    Uses fill=0 (black) on white background.
    
    Args:
        img_or_draw: PIL Image or ImageDraw.Draw object
        wmo_code: WMO weather code
        x, y: top-left position
        size: icon size in pixels
    """
    if isinstance(img_or_draw, Image.Image):
        draw = ImageDraw.Draw(img_or_draw)
    else:
        draw = img_or_draw
    draw_sun = False
    draw_cloud = False
    draw_rain = False
    draw_snow = False
    draw_lightning = False
    draw_fog = False
    draw_drizzle = False
    
    if wmo_code == 0:
        draw_sun = True
    elif wmo_code in (1, 2):
        draw_sun = True
        draw_cloud = True
    elif wmo_code == 3:
        draw_cloud = True
    elif wmo_code in (45, 48):
        draw_fog = True
    elif wmo_code in (51, 53, 55, 56, 57):
        draw_cloud = True
        draw_drizzle = True
    elif wmo_code in (61, 63, 65, 66, 67):
        draw_cloud = True
        draw_rain = True
    elif wmo_code in (71, 73, 75, 77):
        draw_cloud = True
        draw_snow = True
    elif wmo_code in (80, 81, 82):
        draw_cloud = True
        draw_rain = True
    elif wmo_code in (85, 86):
        draw_cloud = True
        draw_snow = True
    elif wmo_code == 95:
        draw_cloud = True
        draw_lightning = True
    elif wmo_code in (96, 99):
        draw_cloud = True
        draw_lightning = True
        draw_drizzle = True

    def do_draw_sun(cx, cy, r):
        # filled circle center
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=0)
        # 8 short thick lines radiating
        ray_len = r * 1.8
        for i in range(8):
            angle = i * (math.pi / 4)
            x1 = cx + math.cos(angle) * (r * 1.2)
            y1 = cy + math.sin(angle) * (r * 1.2)
            x2 = cx + math.cos(angle) * ray_len
            y2 = cy + math.sin(angle) * ray_len
            draw.line((x1, y1, x2, y2), fill=0, width=max(1, int(size * 0.05)))

    def do_draw_cloud(bx, by, w, h):
        # two overlapping ellipses (one bigger bottom, one smaller top-left)
        # To make it look like a single cloud, we can use a third ellipse to fill the gap.
        draw.ellipse((bx, by + h*0.3, bx + w, by + h), fill=0)
        draw.ellipse((bx + w*0.1, by, bx + w*0.6, by + h*0.7), fill=0)
        draw.ellipse((bx + w*0.4, by + h*0.1, bx + w*0.9, by + h*0.8), fill=0)

    if draw_fog:
        # 3 horizontal lines
        lw = size * 0.8
        lh = max(1, int(size * 0.08))
        lx = x + (size - lw) / 2
        for i in range(3):
            ly = y + size * 0.3 + i * (size * 0.2)
            draw.rectangle((lx, ly, lx + lw, ly + lh), fill=0)
            
    if draw_sun and not draw_cloud:
        do_draw_sun(x + size/2, y + size/2, size * 0.25)
    elif draw_sun and draw_cloud:
        do_draw_sun(x + size*0.7, y + size*0.3, size * 0.2)
        do_draw_cloud(x + size*0.1, y + size*0.4, size*0.7, size*0.5)
    elif draw_cloud:
        do_draw_cloud(x + size*0.15, y + size*0.2, size*0.7, size*0.5)
        
    if draw_cloud:
        base_y = y + size * 0.7
        if draw_rain:
            # 3-4 short vertical lines below cloud
            for i in range(3):
                lx = x + size * 0.3 + i * (size * 0.2)
                draw.line((lx, base_y, lx - size*0.05, base_y + size*0.2), fill=0, width=max(1, int(size*0.05)))
        if draw_drizzle:
            # small dots
            for i in range(3):
                lx = x + size * 0.3 + i * (size * 0.2)
                draw.ellipse((lx - size*0.02, base_y, lx + size*0.02, base_y + size*0.04), fill=0)
        if draw_snow:
            # 3-4 dots/small circles below cloud
            for i in range(3):
                lx = x + size * 0.3 + i * (size * 0.2)
                draw.ellipse((lx - size*0.03, base_y + size*0.05, lx + size*0.03, base_y + size*0.11), fill=0)
        if draw_lightning:
            # zigzag line (3 points) below cloud
            lx = x + size * 0.5
            ly = base_y
            draw.line((lx, ly, lx - size*0.1, ly + size*0.15, lx + size*0.1, ly + size*0.15, lx, ly + size*0.3), fill=0, width=max(1, int(size*0.05)))
