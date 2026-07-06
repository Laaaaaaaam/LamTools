from __future__ import annotations

import base64
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any


@dataclass
class ContactSheet:
    data_url: str
    item_indices: list[int]
    item_count: int
    width: int
    height: int


def build_review_contact_sheets(
    items: list[dict[str, Any]],
    *,
    max_items_per_sheet: int = 4,
) -> list[ContactSheet]:
    if max_items_per_sheet < 1:
        max_items_per_sheet = 4
    sheets: list[ContactSheet] = []
    for start in range(0, len(items), max_items_per_sheet):
        chunk = items[start:start + max_items_per_sheet]
        sheet = _build_one_sheet(chunk)
        if sheet:
            sheets.append(sheet)
    return sheets


def _build_one_sheet(items: list[dict[str, Any]]) -> ContactSheet | None:
    if not items:
        return None
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None

    font_large, font_small = _load_fonts()
    cell_w = 860
    cell_h = 820
    label_h = 82
    gap = 18
    margin = 24
    count = len(items)
    cols = _column_count(count)
    rows = (count + cols - 1) // cols
    width = margin * 2 + cols * cell_w + (cols - 1) * gap
    height = margin * 2 + rows * (cell_h + label_h) + (rows - 1) * gap
    sheet = Image.new("RGB", (width, height), "#111111")
    draw = ImageDraw.Draw(sheet)

    indices: list[int] = []
    for pos, item in enumerate(items):
        image = _open_image(item)
        if image is None:
            continue
        col = pos % cols
        row = pos // cols
        x = margin + col * (cell_w + gap)
        y = margin + row * (cell_h + label_h + gap)
        label = _label_for_item(item)
        draw.rectangle((x, y, x + cell_w, y + label_h), fill="#000000", outline="#F5F5F5", width=2)
        draw.text((x + 20, y + 18), label, fill="#FFFFFF", font=font_large)
        with image:
            thumb = image.convert("RGB")
            thumb.thumbnail((cell_w, cell_h), Image.LANCZOS)
            bg = Image.new("RGB", (cell_w, cell_h), "#202020")
            bg.paste(thumb, ((cell_w - thumb.width) // 2, (cell_h - thumb.height) // 2))
            sheet.paste(bg, (x, y + label_h))
        draw.rectangle((x, y + label_h, x + cell_w, y + label_h + cell_h), outline="#F5F5F5", width=2)
        if item.get("task"):
            task = str(item.get("task") or "")
            if len(task) > 36:
                task = task[:35] + "..."
            draw.rectangle((x + 10, y + label_h + cell_h - 44, x + cell_w - 10, y + label_h + cell_h - 10), fill="#000000")
            draw.text((x + 20, y + label_h + cell_h - 38), task, fill="#E5E5E5", font=font_small)
        index = item.get("index")
        if isinstance(index, int):
            indices.append(index)

    buffer = BytesIO()
    sheet.save(buffer, format="PNG", optimize=True)
    payload = base64.b64encode(buffer.getvalue()).decode("ascii")
    return ContactSheet(
        data_url=f"data:image/png;base64,{payload}",
        item_indices=indices,
        item_count=count,
        width=width,
        height=height,
    )


def _column_count(count: int) -> int:
    if count <= 1:
        return 1
    if count == 2:
        return 2
    if count == 3:
        return 3
    return 2


def _load_fonts() -> tuple[Any, Any]:
    from PIL import ImageFont

    candidates = [
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/simsun.ttc"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    font_path = next((path for path in candidates if path.exists()), None)
    if font_path:
        return ImageFont.truetype(str(font_path), 44), ImageFont.truetype(str(font_path), 28)
    return ImageFont.load_default(), ImageFont.load_default()


def _open_image(item: dict[str, Any]) -> Any | None:
    try:
        from PIL import Image
    except Exception:
        return None
    raw = str(item.get("image_data_url") or item.get("url") or "")
    if raw.startswith("data:image") and "," in raw:
        try:
            payload = raw.split(",", 1)[1]
            return Image.open(BytesIO(base64.b64decode(payload)))
        except Exception:
            return None
    path = item.get("path")
    if path:
        try:
            return Image.open(path)
        except Exception:
            return None
    return None


def _label_for_item(item: dict[str, Any]) -> str:
    index = item.get("index")
    prefix = f"图{index}" if isinstance(index, int) else "图?"
    name = str(item.get("material_name") or item.get("label") or "").strip()
    if name.startswith(prefix):
        return name
    return f"{prefix} {name}".strip()
