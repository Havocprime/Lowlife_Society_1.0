from __future__ import annotations
from io import BytesIO
from typing import Iterable, Tuple, Optional, List
from PIL import Image, ImageDraw, ImageFont

def _open_rgba(buf: bytes) -> Image.Image:
    return Image.open(BytesIO(buf)).convert("RGBA")

def compose_layers(
    base_bytes: bytes,
    overlay_bytes_list: Iterable[bytes],
    positions: Optional[Iterable[Tuple[int, int]]] = None,
    sizes: Optional[Iterable[Tuple[int, int]]] = None,
    text_overlays: Optional[List[dict]] = None,
) -> BytesIO:
    """
    Composites overlays onto base in order, respecting alpha.
    - positions: list of (x,y) for each overlay (default 0,0)
    - sizes: list of (w,h) to resize each overlay (optional)
    - text_overlays: [{"text": "...", "xy": (x,y), "font_path": "GAME/assets/Roboto-Bold.ttf", "size": 28}]
    Returns a BytesIO PNG.
    """
    base = _open_rgba(base_bytes)
    out = base.copy()

    positions = list(positions or [])
    sizes = list(sizes or [])

    overlays = list(overlay_bytes_list)
    for idx, ob in enumerate(overlays):
        ov = _open_rgba(ob)
        if idx < len(sizes) and sizes[idx]:
            w, h = sizes[idx]
            ov = ov.resize((w, h), Image.LANCZOS)
        x = positions[idx][0] if idx < len(positions) and positions[idx] else 0
        y = positions[idx][1] if idx < len(positions) and positions[idx] else 0
        out.alpha_composite(ov, dest=(x, y))

    # Optional text (e.g., damage numbers)
    if text_overlays:
        draw = ImageDraw.Draw(out)
        for t in text_overlays:
            txt = t.get("text", "")
            xy = t.get("xy", (0, 0))
            size = int(t.get("size", 28))
            font_path = t.get("font_path")
            try:
                font = ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()
            except Exception:
                font = ImageFont.load_default()
            draw.text(xy, txt, fill=(255, 255, 255, 255), font=font)

    buf = BytesIO()
    out.save(buf, format="PNG")
    buf.seek(0)
    return buf
