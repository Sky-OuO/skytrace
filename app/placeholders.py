"""程序绘制的示例图。每张构图和颜色都按题材变化，并标明示例图。"""

import hashlib
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = (
    Path("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"),
    Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
)

SIZES = ((900, 1200), (860, 1140), (960, 960), (1100, 820), (880, 1320))


def _font(size: int) -> ImageFont.ImageFont:
    for path in FONT_CANDIDATES:
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _rgb(digest: bytes, start: int, shift: int = 0) -> tuple[int, int, int]:
    return tuple(48 + (digest[start + offset] + shift) % 176 for offset in range(3))  # type: ignore[return-value]


def render_placeholder(slug: str, index: int, channel: str, caption: str) -> tuple[bytes, int, int]:
    digest = hashlib.sha256(f"{slug}:{index}".encode()).digest()
    width, height = SIZES[(digest[0] + index) % len(SIZES)]
    image = Image.new("RGB", (width, height), _rgb(digest, 1))
    draw = ImageDraw.Draw(image)
    if channel == "portrait":
        _draw_portrait(draw, width, height, digest, slug)
    else:
        _draw_landscape(draw, width, height, digest)
    label = _font(max(22, width // 28))
    small = _font(max(18, width // 36))
    draw.rectangle((0, height - 92, width, height), fill=(20, 16, 12))
    draw.text((24, height - 78), caption[:18], fill=(243, 239, 231), font=label)
    draw.text((24, height - 40), "示例图", fill=(232, 196, 156), font=small)
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue(), width, height


def _draw_portrait(draw: ImageDraw.ImageDraw, width: int, height: int, digest: bytes, slug: str) -> None:
    room = _rgb(digest, 4, 20)
    draw.rectangle((0, 0, width, height), fill=room)
    cool = _rgb(digest, 7, 80)
    side = "right" if digest[10] % 2 else "left"
    if "night" in slug:
        draw.rectangle((0, 0, width, height), fill=(18, 22, 34))
        for n in range(18):
            x = 30 + (digest[n % 8] * (n + 3)) % (width - 40)
            y = 30 + (digest[(n + 3) % 8] * (n + 5)) % (height // 2)
            radius = 4 + n % 7
            color = (240, 210, 140) if n % 2 == 0 else (140, 180, 230)
            draw.ellipse((x, y, x + radius, y + radius), fill=color)
    else:
        win_w = int(width * 0.34)
        margin = int(width * 0.08)
        x0 = width - margin - win_w if side == "right" else margin
        draw.rectangle((x0, int(height * 0.08), x0 + win_w, int(height * 0.78)), fill=cool)
        draw.rectangle((x0 + 12, int(height * 0.1), x0 + win_w - 12, int(height * 0.76)), outline=(255, 255, 255), width=3)
    skin = (214, 176, 150)
    cx = int(width * (0.38 if side == "right" else 0.62))
    cy = int(height * 0.42)
    head = int(width * 0.07)
    draw.ellipse((cx - head, cy - head, cx + head, cy + head), fill=skin)
    shoulder = int(width * 0.16)
    draw.pieslice(
        (cx - shoulder, cy + head // 2, cx + shoulder, cy + int(height * 0.28)),
        start=200,
        end=340,
        fill=(digest[12] % 80 + 40, digest[13] % 60 + 40, digest[14] % 50 + 50),
    )


def _draw_landscape(draw: ImageDraw.ImageDraw, width: int, height: int, digest: bytes) -> None:
    sky = _rgb(digest, 3, 30)
    draw.rectangle((0, 0, width, height), fill=sky)
    horizon = int(height * (0.42 + (digest[9] % 12) / 100))
    land = _rgb(digest, 6, 10)
    peaks = []
    x = 0
    while x <= width:
        rise = int(height * (0.12 + (digest[(x // 50) % 8] % 20) / 100))
        peaks.append((x, horizon - rise))
        x += 70 + digest[(x // 40) % 8] % 50
    peaks.append((width, horizon))
    draw.polygon([(0, height), *peaks, (width, height)], fill=land)
    if digest[11] % 3 == 0:
        water = tuple(max(0, channel - 30) for channel in sky)
        draw.rectangle((0, horizon, width, height), fill=water)
        draw.line((0, horizon, width, horizon), fill=(255, 255, 255), width=2)
    sun_x = int(width * (0.2 + (digest[15] % 60) / 100))
    sun_y = int(horizon * 0.55)
    radius = 28 + digest[16] % 24
    draw.ellipse((sun_x, sun_y, sun_x + radius, sun_y + radius), fill=(255, 214, 140))
