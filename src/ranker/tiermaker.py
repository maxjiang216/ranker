"""Import items from a saved tiermaker.com page, and render a tier list as a PNG.

tiermaker.com sits behind a Cloudflare challenge, so a backend cannot scrape a template
URL directly. The supported flow is: open the template in a browser, **Save As ->
"Webpage, Complete"**, then point us at the saved ``.html`` file. The browser (which
passes Cloudflare) writes the item images into a sibling ``<page>_files/`` folder; we
parse the HTML for the item order/labels and read those local images.

Rendering the final tier list does **not** need tiermaker at all -- :func:`render_tierlist`
draws a tiermaker-style image (colored S/A/B/... rows with thumbnails) with Pillow.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.parse import unquote, urlparse

# Container ids/classes that hold the draggable item images on a tiermaker page.
_POOL_IDS = {
    "images-to-sort",
    "untiered",
    "sortable-images",
    "image-container",
    "default-container",
}
_POOL_CLASSES = {"sortable", "untiered", "character", "tier-image", "item"}
# Substrings in an image filename that mark it as site chrome, not a ranked item.
_JUNK = ("logo", "sprite", "icon", "blank", "spacer", "pixel", "favicon", "avatar", "ad-")
_IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif")


@dataclass
class ParsedItem:
    """One item scraped from a saved tiermaker page."""

    name: str
    src: str  # raw ``src`` as written in the HTML (relative path or absolute URL)


def _classes(attrs: Dict[str, str]) -> set:
    return set((attrs.get("class") or "").split())


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._stack: List[bool] = []  # is each open ancestor an item pool?
        self.imgs: List[Tuple[Dict[str, str], bool]] = []  # (attrs, in_pool)

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "img":
            in_pool = any(self._stack)
            self.imgs.append((a, in_pool))
            return
        # Track only containers that can nest (skip void/self-closing tags).
        if tag in ("br", "hr", "input", "meta", "link", "source"):
            return
        is_pool = (a.get("id", "") in _POOL_IDS) or bool(_classes(a) & _POOL_CLASSES)
        self._stack.append(is_pool or (self._stack[-1] if self._stack else False))

    def handle_endtag(self, tag):
        if tag in ("img", "br", "hr", "input", "meta", "link", "source"):
            return
        if self._stack:
            self._stack.pop()


def _label_from_src(src: str) -> str:
    base = os.path.basename(urlparse(src).path)
    stem = unquote(os.path.splitext(base)[0])
    stem = re.sub(r"[_\-]+", " ", stem).strip()
    return stem


def _looks_like_item(src: str, in_pool: bool) -> bool:
    if not src or src.startswith("data:"):
        return False
    low = urlparse(src).path.lower()
    if not low.endswith(_IMG_EXT):
        return False
    if in_pool:
        return True
    return not any(j in low for j in _JUNK)


def parse_saved_page(html_path: str) -> List[ParsedItem]:
    """Parse a saved tiermaker page into an ordered, de-duplicated list of items.

    Prefers images inside a recognized item-pool container; if the page exposes none,
    falls back to every content image that is not obvious site chrome. Labels come from
    the image ``alt``/``title`` attribute, else the filename.
    """
    text = Path(html_path).read_text(encoding="utf-8", errors="replace")
    parser = _PageParser()
    parser.feed(text)

    pooled = [(a, p) for a, p in parser.imgs if p]
    candidates = pooled if pooled else parser.imgs

    items: List[ParsedItem] = []
    seen = set()
    for attrs, in_pool in candidates:
        src = (attrs.get("src") or attrs.get("data-src") or "").strip()
        if not _looks_like_item(src, in_pool) or src in seen:
            continue
        seen.add(src)
        name = (attrs.get("alt") or attrs.get("title") or "").strip()
        if not name:
            name = _label_from_src(src)
        if not name:
            name = f"item-{len(items) + 1}"
        items.append(ParsedItem(name=name, src=src))
    return _dedupe_names(items)


def _dedupe_names(items: List[ParsedItem]) -> List[ParsedItem]:
    counts: Dict[str, int] = {}
    out = []
    for it in items:
        n = it.name
        if n in counts:
            counts[n] += 1
            n = f"{it.name} ({counts[it.name]})"
        else:
            counts[n] = 0
        out.append(ParsedItem(name=n, src=it.src))
    return out


def resolve_src(src: str, html_path: str) -> Optional[Path]:
    """Resolve an image ``src`` to a local file next to the saved page, or ``None`` if it
    is a remote URL (or the local file is missing)."""
    if urlparse(src).scheme in ("http", "https"):
        return None
    rel = unquote(urlparse(src).path if "://" in src else src)
    p = (Path(html_path).parent / rel).resolve()
    return p if p.is_file() else None


# -- PNG rendering ------------------------------------------------------------

# Classic tiermaker palette, best tier first; cycles if there are more tiers than colors.
_TIER_COLORS = [
    (255, 127, 127),  # S  red
    (255, 191, 127),  # A  orange
    (255, 223, 127),  # B  gold
    (255, 255, 127),  # C  yellow
    (191, 255, 127),  # D  yellow-green
    (127, 255, 127),  # E  green
    (127, 255, 255),  # F  cyan
    (127, 191, 255),  # G  blue
    (191, 159, 255),  # H  purple
]
_TIER_LETTERS = ["S", "A", "B", "C", "D", "E", "F", "G", "H"]


def tier_labels(k: int) -> List[str]:
    """Default tier labels: S, A, B, C, ... then ``Tier N`` once letters run out."""
    return [_TIER_LETTERS[i] if i < len(_TIER_LETTERS) else f"T{i + 1}" for i in range(k)]


def render_tierlist(
    tiers: Sequence[Sequence[str]],
    image_paths: Dict[str, Path],
    out_path: str,
    *,
    labels: Optional[Sequence[str]] = None,
    thumb: int = 80,
    per_row: int = 12,
    label_w: int = 90,
    pad: int = 2,
) -> str:
    """Render ``tiers`` (each a list of item names, best first) to a tier-list PNG.

    ``image_paths`` maps item name -> local image file; items without an image are drawn
    as a labeled box. Raises :class:`RuntimeError` with install hint if Pillow is missing.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:  # pragma: no cover - exercised via message only
        raise RuntimeError(
            "Rendering a tier-list PNG needs Pillow. Install it with: uv add pillow"
        ) from exc

    labels = list(labels) if labels is not None else tier_labels(len(tiers))
    font = ImageFont.load_default()
    cell = thumb + 2 * pad

    def row_height(n: int) -> int:
        rows = max(1, math.ceil(n / per_row))
        return rows * cell

    width = label_w + per_row * cell
    height = sum(row_height(len(t)) for t in tiers) or cell
    img = Image.new("RGB", (width, height), (32, 32, 32))
    draw = ImageDraw.Draw(img)

    def draw_centered(box, text):
        x0, y0, x1, y1 = box
        try:
            tb = draw.textbbox((0, 0), text, font=font)
            tw, th = tb[2] - tb[0], tb[3] - tb[1]
        except Exception:  # very old Pillow
            tw, th = draw.textsize(text, font=font)
        draw.text(
            ((x0 + x1 - tw) / 2, (y0 + y1 - th) / 2), text, fill=(0, 0, 0), font=font
        )

    y = 0
    for idx, tier in enumerate(tiers):
        h = row_height(len(tier))
        color = _TIER_COLORS[idx % len(_TIER_COLORS)]
        draw.rectangle([0, y, label_w - 1, y + h - 1], fill=color)
        label = labels[idx] if idx < len(labels) else f"T{idx + 1}"
        draw_centered((0, y, label_w, y + h), label)

        for j, name in enumerate(tier):
            col = j % per_row
            row = j // per_row
            x = label_w + col * cell
            cy = y + row * cell
            box = [x + pad, cy + pad, x + pad + thumb, cy + pad + thumb]
            path = image_paths.get(name)
            placed = False
            if path is not None and Path(path).is_file():
                try:
                    with Image.open(path) as im:
                        im = im.convert("RGB")
                        im.thumbnail((thumb, thumb))
                        ox = box[0] + (thumb - im.width) // 2
                        oy = box[1] + (thumb - im.height) // 2
                        img.paste(im, (ox, oy))
                        placed = True
                except Exception:
                    placed = False
            if not placed:
                draw.rectangle(box, fill=(64, 64, 64), outline=(110, 110, 110))
                draw_caption(draw, box, name, font)
        y += h

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path


def draw_caption(draw, box, text, font) -> None:
    """Draw a short, truncated caption centered in ``box`` (light text on dark box)."""
    x0, y0, x1, y1 = box
    short = text if len(text) <= 10 else text[:9] + "…"
    try:
        tb = draw.textbbox((0, 0), short, font=font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
    except Exception:
        tw, th = draw.textsize(short, font=font)
    draw.text(
        ((x0 + x1 - tw) / 2, (y0 + y1 - th) / 2), short, fill=(230, 230, 230), font=font
    )
