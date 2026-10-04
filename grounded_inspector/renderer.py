"""Draw defect annotations from a verdict onto the input image.

Reproduces QMSInspector's marking style so GroundedInspector output looks the
same:
  * the defect region is SEGMENTED to hug the actual defect pixels inside the
    box (rust colour threshold for corrosion, edge/Canny for geometry defects),
    falling back to the plain box when no method applies or segmentation fails;
    dark defects (dark_mark / dark_spot) are drawn as a plain tight box only -
    never an organic polygon;
  * a 30% translucent colour FILL over that region;
  * a high-contrast triple-stroke LOCATOR outline (black halo -> white ->
    colour) around it, thicker for the primary (highest-severity) defect;
  * a dark label chip with white text.
The segmentation/marking here mirrors QMSInspector/inspector/renderer.py. It is a
rendering concern only: the engine (me today, the Anthropic API later) supplies
the verdict geometry; this module draws it. cv2 is optional - without it the
renderer degrades to plain filled boxes.
"""
from __future__ import annotations

import os
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from . import loader as C

try:  # cv2 powers the QMS-style segmentation + translucent fill; optional.
    import cv2
except Exception:  # noqa
    cv2 = None

# Per-category segmentation method (QMS decides this by defect type at draw time).
# Values map to _segment_defect(); anything absent draws as a plain filled box.
_SEG_BY_CATEGORY = {
    "corrosion": "rust",
    # Dark defects (dark_mark / dark_spot) draw as a plain tight BOX, never an organic
    # segmented polygon (user requirement: no polygon for dark marks).
    "dent": "edge",
    "edge_chip": "edge",
    "missing_punch": "edge",
    "out_of_round": "edge",
    # QMS traces the serration hole (a circle). Embossing defects draw as a plain
    # bounding box only (no inner character segmentation).
    "serration_missing": "circle",
}
_FILL_ALPHA = 0.30  # QMS blends the colour overlay at 30%.


_STATUS_COLOR = {  # RGB
    "DEFECT": (239, 68, 68),
    "OK": (34, 197, 94),
    "NEEDS_REVIEW": (245, 158, 11),
}


def _catalog_colors() -> dict:
    """category(lower) -> RGB from global catalog + all part configs (BGR stored)."""
    colors = {}
    cat = C.load_global_catalog()
    for name, spec in cat.get("defects", {}).items():
        bgr = spec.get("color")
        if bgr:
            colors[name.lower()] = (bgr[2], bgr[1], bgr[0])
    for part in C.list_parts():
        for name, spec in (part.get("defects", {}) or {}).items():
            bgr = spec.get("color")
            if bgr:
                colors[name.lower()] = (bgr[2], bgr[1], bgr[0])
    return colors


def _font(size: int):
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:  # noqa
            continue
    return ImageFont.load_default()


def _text_size(draw, text, font):
    try:
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        return r - l, b - t
    except Exception:  # noqa
        return draw.textlength(text, font=font), size if (size := 12) else 12


def _text_box(draw, text, font, padx=6, pady=5):
    """Return (bw, bh, dx, dy) for a padded chip that FULLY contains `text`.
    dx/dy compensate for the font bbox origin offset (l, t) so glyphs - including
    descenders like 'g'/'p' and the top of tall caps - are never clipped."""
    try:
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
    except Exception:  # noqa
        w = int(draw.textlength(text, font=font)); h = 12; l = t = 0; r = w; b = h
    bw = (r - l) + 2 * padx
    bh = (b - t) + 2 * pady
    return bw, bh, padx - l, pady - t


def _focus_color(col):
    """High-contrast outline colour: swap out low-saturation / very bright colours
    for an azure that stays visible on bright metal (mirrors QMS focus_color_for)."""
    r, g, b = int(col[0]), int(col[1]), int(col[2])
    spread = max(r, g, b) - min(r, g, b)
    mean = (r + g + b) / 3.0
    if spread < 40 or mean > 200:
        return (0, 160, 255)  # azure (RGB)
    return (r, g, b)


def _catalog_display_names() -> dict:
    """category(lower) -> QMS display name from the config bundle (global + parts).

    Lets a bundle-only verdict that carries just `category` still render the exact
    QMS label (e.g. incomplete_embossing -> 'Incomplete/Shallow Embossing', dark_spot
    -> 'Dark Spots'), without the model or any harness having to inject the string.
    """
    names = {}
    cat = C.load_global_catalog()
    for name, spec in cat.get("defects", {}).items():
        dn = spec.get("display_name")
        if dn:
            names[name.lower()] = dn
    for part in C.list_parts():
        for name, spec in (part.get("defects", {}) or {}).items():
            dn = spec.get("display_name")
            if dn:
                names[name.lower()] = dn
    return names


_DISPLAY_CACHE = None


def _display_name(cat: str) -> str:
    """QMS-style human-readable defect name. Prefer the exact display_name declared
    in the config bundle; fall back to title-casing the category."""
    global _DISPLAY_CACHE
    if _DISPLAY_CACHE is None:
        try:
            _DISPLAY_CACHE = _catalog_display_names()
        except Exception:  # noqa
            _DISPLAY_CACHE = {}
    key = str(cat).strip().lower()
    if key in _DISPLAY_CACHE:
        return _DISPLAY_CACHE[key]
    return str(cat).replace("_", " ").strip().title()


def _confidence_pct(d) -> Optional[int]:
    """Normalize a verdict's confidence (fraction 0..1 or percent 0..100) to an
    int percent, or None if absent/unparseable. Shared by every label path so
    the rendered defect marks show the same confidence metadata as the verdict."""
    conf = d.get("confidence")
    if conf is None:
        return None
    try:
        conf = float(conf)
    except (TypeError, ValueError):
        return None
    pct = conf * 100 if conf <= 1.0 else conf
    return int(round(pct))


def _defect_label(d, is_primary: bool) -> str:
    """QMS label: '* Serration Missing  [P4]  92%' (star = primary, [P#] = priority,
    trailing percent = model confidence, when the verdict carries one)."""
    tag = ""
    sev = d.get("severity")
    if isinstance(sev, (int, float)):
        tag = f"  [P{int(sev)}]"
    name = d.get("display_name") or _display_name(d.get("category", "?"))
    pct = _confidence_pct(d)
    conf_tag = f"  {pct}%" if pct is not None else ""
    return ("* " if is_primary else "") + name + tag + conf_tag


def _bbox_px(bbox, W, H):
    bx, by, bw, bh = bbox
    x0, y0 = max(0, int(bx * W)), max(0, int(by * H))
    x1, y1 = min(W, int((bx + bw) * W)), min(H, int((by + bh) * H))
    return x0, y0, x1, y1


def _segment_defect(arr_rgb, bbox, method):
    """Return pixel contours (list of Nx1x2 int32, full-image coords) segmenting the
    defect inside bbox, hugging the real defect pixels. [] if unavailable/failed.

    Ported from QMSInspector: colour threshold for rust, gray threshold for dark
    defects, Canny edges for geometry. Keeps GroundedInspector's marks identical
    to QMS instead of a coarse rectangle."""
    if cv2 is None or method not in ("rust", "dark", "edge", "geometry", "circle"):
        return []
    H, W = arr_rgb.shape[:2]
    x0, y0, x1, y1 = _bbox_px(bbox, W, H)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return []
    roi = arr_rgb[y0:y1, x0:x1]
    area = roi.shape[0] * roi.shape[1]
    if method == "circle":
        # QMS localizes the serration hole with HoughCircles and draws a clean
        # circle. Detect the hole here; fall back to an ellipse inscribed in the
        # box. Returns one smooth circular contour (never the jagged Canny mess).
        rh, rw = roi.shape[:2]
        gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
        gray = cv2.medianBlur(gray, 5)
        cx, cy, rad = rw / 2.0, rh / 2.0, min(rw, rh) * 0.46
        circles = cv2.HoughCircles(
            gray, cv2.HOUGH_GRADIENT, dp=1.2, minDist=max(rw, rh),
            param1=110, param2=28,
            minRadius=int(min(rw, rh) * 0.20), maxRadius=int(min(rw, rh) * 0.62))
        if circles is not None:
            c = circles[0][0]
            cx, cy, rad = float(c[0]), float(c[1]), float(c[2])
        # The locator must trace the bore itself. Do not inflate the detected
        # radius: the rendered circle should coincide with the hole/bore boundary,
        # rather than surrounding it with an oversized ring.
        rad = min(rad, min(rw, rh) * 0.5)
        poly = cv2.ellipse2Poly((int(x0 + cx), int(y0 + cy)),
                                (int(rad), int(rad)), 0, 0, 360, 6)
        return [poly.reshape(-1, 1, 2).astype(np.int32)]
    mask = None
    if method == "rust":
        hsv = cv2.cvtColor(roi, cv2.COLOR_RGB2HSV)
        mask = cv2.inRange(hsv, (3, 40, 40), (25, 255, 230))
    elif method == "dark":
        gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
        thr = max(40, int(np.mean(gray) - 0.6 * np.std(gray)))
        mask = cv2.inRange(gray, 0, thr)
        # Dark defects are often DIFFUSE speckle clusters: individual specks are tiny
        # and would be dropped by the area filter, causing a fallback to a filled box.
        # Merge neighbouring specks into one organic blob so we hug the cluster (like
        # QMS's ground-truth polygon) instead of painting the whole bbox.
        k = max(5, int(round(min(roi.shape[0], roi.shape[1]) * 0.12)) | 1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
        mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1)
    elif method in ("edge", "geometry"):
        gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        edges = cv2.Canny(gray, 40, 120)
        edges = cv2.dilate(edges, np.ones((5, 5), np.uint8), iterations=2)
        mask = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    if mask is None:
        return []
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # Dark speckle clusters can be modest after merging; use a lower floor so we still
    # hug the blob rather than falling back to a filled bbox.
    min_area = max(20, 0.004 * area) if method == "dark" else max(30, 0.01 * area)
    cnts = [c for c in cnts if cv2.contourArea(c) >= min_area]
    cnts.sort(key=cv2.contourArea, reverse=True)
    if method == "dark" and cnts:
        # A loose/oversized bbox can let segmentation pick up unrelated dark specks
        # far from the real mark; keeping them would drag the recomputed outline
        # across the whole face (QMS draws a tight box). Keep the dominant blob and
        # only genuinely adjacent specks (within a small, image-relative reach), so
        # the mark stays tight even when the supplied box is too big.
        reach = 0.12 * min(W, H)
        c0 = cnts[0].reshape(-1, 2).mean(axis=0)
        cnts = [cnts[0]] + [
            c for c in cnts[1:]
            if float(np.linalg.norm(c.reshape(-1, 2).mean(axis=0) - c0)) <= reach
        ]
    return [(c + np.array([[x0, y0]])).astype(np.int32) for c in cnts[:3]]


def _focus_outline_cv(arr, geom, col, thickness):
    """Thin locator outline (1px dark halo -> colour) on a numpy RGB array. geom is
    either a (x0,y0,x1,y1) box tuple or a list of cv2 contours. Kept deliberately
    THIN (no heavy triple band) so the mark is clearly visible but not bold."""
    edge = _focus_color(col)
    halo, core = thickness + 1, thickness
    if isinstance(geom, tuple):
        x0, y0, x1, y1 = geom
        cv2.rectangle(arr, (x0, y0), (x1, y1), (0, 0, 0), halo, cv2.LINE_AA)
        cv2.rectangle(arr, (x0, y0), (x1, y1), edge, core, cv2.LINE_AA)
    else:
        cv2.polylines(arr, geom, True, (0, 0, 0), halo, cv2.LINE_AA)
        cv2.polylines(arr, geom, True, edge, core, cv2.LINE_AA)


def _instance_style_side(side, W, H):
    """Mark styling from a part's characteristic pixel size `side`."""
    gside = min(W, H)
    fscale = max(12, int(min(gside * 0.028, side * 0.075)))
    thickness = max(2, int(round(side * 0.012)))
    line_scale = max(0.35, min(1.0, side / gside))
    return _font(fscale), thickness, line_scale


def _instance_style(inst, W, H):
    """Size marks to an INSTANCE's region, not the whole frame, so a small part in
    a multi-part photo doesn't get oversized labels/outlines. When `inst` is None
    (single-part mode) or the part fills the frame, this reduces to the whole-image
    scale (no regression). Returns (font, base_thickness, line_scale)."""
    side = min(W, H)
    if inst and isinstance(inst.get("instance_bbox"), list) and len(inst["instance_bbox"]) == 4:
        x, y, w, h = inst["instance_bbox"]
        side = max(1.0, min(abs(w) * W, abs(h) * H))
    return _instance_style_side(side, W, H)


def _fill_and_outline(arr, overlay, d, W, H, colors, is_primary, base_thickness=2,
                      multi_part=False):
    """QMS-style mark for a box/region defect. Returns
    (label_anchor_xy, label_text, col, region_rect) for the PIL label pass, or None.

    - single part in the image  -> bounding box + INNER marking (segmentation
      contour outline + translucent fill): the full QMS look.
    - multiple parts in the image -> a thin BOUNDING BOX only (minimum thickness,
      just visible) so small parts don't get heavy/ragged inner strokes."""
    bbox = d.get("bbox") or [0, 0, 0, 0]
    if len(bbox) != 4:
        return None
    col = colors.get(str(d.get("category", "")).lower(), (245, 158, 11))
    x0, y0, x1, y1 = _bbox_px(bbox, W, H)
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))

    method = d.get("seg") or _SEG_BY_CATEGORY.get(str(d.get("category", "")).lower())
    contours = ([] if multi_part else
                (_segment_defect(arr, bbox, method) if (method and cv2 is not None) else []))

    if cv2 is not None:
        if contours:
            cv2.fillPoly(overlay, contours, col)
            pts = np.vstack([c.reshape(-1, 2) for c in contours])
            x0, y0, x1, y1 = int(pts[:, 0].min()), int(pts[:, 1].min()), \
                int(pts[:, 0].max()), int(pts[:, 1].max())
        elif not multi_part:
            cv2.rectangle(overlay, (x0, y0), (x1, y1), col, -1)

    pad = 6
    rx0, ry0 = max(0, x0 - pad), max(0, y0 - pad)
    rx1, ry1 = min(W - 1, x1 + pad), min(H - 1, y1 + pad)
    if cv2 is not None:
        if multi_part:
            # thin bounding box only - uniform thin weight for every part
            core = 1
            _focus_outline_cv(arr, (rx0, ry0, rx1, ry1), col, core)
        else:
            # single part: bounding box + inner marking (contour outline), uniform
            # thin weight (NOT thicker for the primary) so multiple defects in one
            # image all read the same, not one bold + one thin.
            core = 2
            if contours:
                _focus_outline_cv(arr, contours, col, core)
            _focus_outline_cv(arr, (rx0, ry0, rx1, ry1), col, core)

    label = _defect_label(d, is_primary)
    return (rx0, ry0), label, col, (rx0, ry0, rx1, ry1)


def _rects_overlap(a, b):
    return not (a[2] <= b[0] or a[0] >= b[2] or a[3] <= b[1] or a[1] >= b[3])


def _place_label(desired, bw, bh, occupied, W, H):
    """Return a top-left (lx, ly) for a bw x bh label box near `desired` that does
    not overlap any rect in `occupied` (labels/chips already drawn). Tries nudging
    down, then up, then keeps the least-bad spot. Clamps on-image."""
    dx, dy = desired
    lx = max(0, min(int(dx), W - bw))
    ly = max(0, min(int(dy), H - bh))
    if not occupied:
        return lx, ly
    for _ in range(16):
        r = (lx, ly, lx + bw, ly + bh)
        hit = next((o for o in occupied if _rects_overlap(r, o)), None)
        if hit is None:
            return lx, ly
        ly = hit[3] + 2  # drop just below the thing we collided with
        if ly + bh > H:
            break
    # couldn't fit below: try just above the topmost collider
    ly = max(0, min(int(dy), H - bh))
    for _ in range(16):
        r = (lx, ly, lx + bw, ly + bh)
        hit = next((o for o in occupied if _rects_overlap(r, o)), None)
        if hit is None:
            return lx, ly
        ly = hit[1] - bh - 2
        if ly < 0:
            break
    return lx, max(0, min(int(dy), H - bh))


def _draw_label(draw, anchor, label, col, font, W, H, occupied=None):
    bw, bh, dx, dy = _text_box(draw, label, font)
    x0, y0 = anchor
    lx, ly = _place_label((x0, y0 - bh - 4), bw, bh, occupied, W, H)
    draw.rectangle([lx, ly, lx + bw, ly + bh], fill=(12, 18, 28))
    draw.rectangle([lx, ly, lx + bw, ly + bh], outline=col, width=2)
    draw.text((lx + dx, ly + dy), label, fill=(255, 255, 255), font=font)
    if occupied is not None:
        occupied.append((lx, ly, lx + bw, ly + bh))


def _qms_ml_label(d) -> str:
    """QMS ML-ensemble chip text, e.g. 'Line Mark (ML 99%)'. Confidence may be a
    fraction (0..1) or a percent (0..100)."""
    pct = _confidence_pct(d) or 0
    name = d.get("display_name") or _display_name(d.get("category", "?"))
    return f"{name} (ML {pct}%)"


def _draw_qms_ml_chip(draw, label, font, W, H, occupied=None):
    """Draw QMS's red-bordered black chip with white text, pinned to the TOP-LEFT
    corner (how QMSInspector labels ML-ensemble line marks)."""
    bw, bh, dx, dy = _text_box(draw, label, font)
    lx, ly = _place_label((8, 8), bw, bh, occupied, W, H)
    draw.rectangle([lx, ly, lx + bw, ly + bh], fill=(0, 0, 0))
    draw.rectangle([lx, ly, lx + bw, ly + bh], outline=(214, 24, 24),
                   width=max(2, int(min(W, H) * 0.004)))
    draw.text((lx + dx, ly + dy), label, fill=(255, 255, 255), font=font)
    if occupied is not None:
        occupied.append((lx, ly, lx + bw, ly + bh))


def _tighten_to_part(base, box):
    """Shrink a loose instance box to the actual PART silhouette inside it.

    An auto instance_bbox often covers the whole photo tile (part pasted on a sheet
    of paper, itself on a canvas), so the dashed frame looks loose and the name chip
    floats over empty space. Backgrounds (paper, canvas) are smooth and reach the
    tile border; the metal PART is a compact, TEXTURED interior blob (holes, edges,
    embossing, reflections, contact shadow). We threshold a local-texture (std) map
    and take the largest textured component that is NOT the whole tile. If only a
    sparse whole-tile component exists (very low-contrast part), we fall back to a
    percentile ("dense core") bounding box. Falls back to the given box if nothing
    is reliable. Robust to bright/silver parts and two-level backgrounds where a
    plain brightness threshold or a border-seeded GrabCut merges the part into the
    paper. Generalises to the real API: even a loose engine box renders a tight,
    part-hugging frame."""
    x0, y0, x1, y1 = box
    if cv2 is None or (x1 - x0) < 16 or (y1 - y0) < 16:
        return box
    roi = base[y0:y1, x0:x1]
    if roi.size == 0:
        return box
    try:
        h, w = roi.shape[:2]
        scale = min(1.0, 360.0 / float(max(h, w)))
        if scale < 1.0:
            sm = cv2.resize(roi, (max(8, int(w * scale)), max(8, int(h * scale))),
                            interpolation=cv2.INTER_AREA)
        else:
            sm = roi
        g = cv2.cvtColor(sm, cv2.COLOR_RGB2GRAY).astype(np.float32)
        win = max(7, (int(min(sm.shape[0], sm.shape[1]) * 0.04) | 1))
        mean = cv2.boxFilter(g, -1, (win, win))
        sq = cv2.boxFilter(g * g, -1, (win, win))
        std = np.sqrt(np.clip(sq - mean * mean, 0, None))
        std = np.clip(std, 0, 255).astype(np.uint8)
        _, mask = cv2.threshold(std, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        k = max(3, (int(min(sm.shape[0], sm.shape[1]) * 0.035) | 1))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8), iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        n, _lab, stats, _cent = cv2.connectedComponentsWithStats(mask, 8)
        sh, sw = mask.shape
        best = None
        best_area = 0
        for i in range(1, n):
            cx, cy, cw, ch, ar = stats[i]
            if cw > 0.93 * sw and ch > 0.93 * sh:
                continue  # spans the whole tile - not a part
            if ar < 0.01 * sh * sw:
                continue  # speckle
            if ar > best_area:
                best_area = ar
                best = (cx, cy, cw, ch)
        if best is None:
            # dense-core recovery for very low-contrast parts (sparse whole-tile
            # component): use a percentile bbox to drop scattered outliers.
            ys, xs = np.where(mask > 0)
            if len(xs) < 20:
                return box
            cx = np.percentile(xs, 3)
            cy = np.percentile(ys, 3)
            cw = np.percentile(xs, 97) - cx
            ch = np.percentile(ys, 97) - cy
            if cw < 4 or ch < 4:
                return box
            best = (cx, cy, cw, ch)
        inv = 1.0 / scale if scale < 1.0 else 1.0
        rx, ry, rw, rh = (int(best[0] * inv), int(best[1] * inv),
                          int(best[2] * inv), int(best[3] * inv))
    except Exception:
        return box
    frac = (rw * rh) / float((x1 - x0) * (y1 - y0))
    if frac < 0.02 or frac > 0.985:
        return box  # caught noise or the whole tile - keep original
    px, py = int(rw * 0.05), int(rh * 0.05)  # small breathing pad
    nx0 = x0 + max(0, rx - px)
    ny0 = y0 + max(0, ry - py)
    nx1 = x0 + min(x1 - x0, rx + rw + px)
    ny1 = y0 + min(y1 - y0, ry + rh + py)
    return (nx0, ny0, nx1, ny1)


def _draw_instance_frame(draw, inst, box_px, W, H, font):
    """Dashed part-region frame + a part-name chip for an auto instance, using a
    pre-tightened pixel box so the frame hugs the actual part and the chip sits on
    it (never floating in background or clipped off-image)."""
    part = str(inst.get("part", "part"))
    res = inst.get("result", "NEEDS_REVIEW")
    rc = _STATUS_COLOR.get(res, (245, 158, 11))
    if box_px is None:
        return
    x0, y0, x1, y1 = box_px
    x0, x1 = sorted((max(0, int(x0)), min(W, int(x1))))
    y0, y1 = sorted((max(0, int(y0)), min(H, int(y1))))
    if x1 - x0 < 4 or y1 - y0 < 4:
        return
    # dashed rectangle in the instance's status colour (dash scaled to the part)
    dash = max(6, int(min(x1 - x0, y1 - y0) * 0.06))
    for xx in range(x0, x1, dash * 2):
        draw.line([xx, y0, min(xx + dash, x1), y0], fill=rc, width=2)
        draw.line([xx, y1, min(xx + dash, x1), y1], fill=rc, width=2)
    for yy in range(y0, y1, dash * 2):
        draw.line([x0, yy, x0, min(yy + dash, y1)], fill=rc, width=2)
        draw.line([x1, yy, x1, min(yy + dash, y1)], fill=rc, width=2)
    chip = f"{part} · {res}"
    idc = inst.get("identity_confidence")
    if isinstance(idc, (int, float)):
        chip += f" {int(idc * 100)}%"
    cw, ch, dx, dy = _text_box(draw, chip, font)
    # keep the chip on-image, pinned to the part's top-left, and floated ABOVE the
    # frame top edge (with a small gap) so it isn't stuck onto the rim/dashed line.
    lx = int(max(0, min(x0, W - cw)))
    gap = 4
    ly = int(y0 - ch - gap)          # above the frame
    if ly < 0:                        # no room above -> sit just inside the top
        ly = int(min(y0 + gap, H - ch))
    if ly < 0:
        ly = 0
    draw.rectangle([lx, ly, lx + cw, ly + ch], fill=rc)
    draw.text((lx + dx, ly + dy), chip, fill=(255, 255, 255), font=font)
    return (lx, ly, lx + cw, ly + ch)


# --- Verdict safety-net guards (catch a fabricated / hallucinated box before drawing) ---
_OFFPART_MIN_OVERLAP = 0.50   # a box overlapping the part silhouette by less than this is off-part
_MERGE_GAP = 0.05             # normalized max gap between same-category boxes that collapse into one
_MIN_ACTIONABLE_AREA = 0.0004  # normalized area; a lone box smaller than this is a non-actionable speck
_DARK_CATEGORIES = {"dark_mark", "dark_spot"}
_DARK_MIN_CONTENT = 0.02      # a dark_* box needs at least this fraction of genuinely near-black pixels


def _dark_abs(part_ref, category=None):
    """Darkness cutoff (0..255 gray) for a dark_* box's content/segmentation.

    dark_mark is defined as ABSOLUTE near-black, so it keeps the strict cutoff.
    dark_spot is defined RELATIVE to the finish ('clearly darker than the surrounding
    finish'), so on a bright bracket a faint-but-real spot (darker than the metal but
    not near-black) must still qualify - testing it as absolute near-black is what
    silently dropped operator-marked edge/scatter dark spots at draw time."""
    if str(category or "").lower() == "dark_spot":
        return min(165.0, 0.82 * float(part_ref))
    return min(110.0, 0.55 * float(part_ref))


def _has_dark_content(base, bbox, part_ref, W, H, category=None):
    """True if a dark_* box actually contains pixels darker than the finish. dark_mark
    is judged ABSOLUTELY (near-black vs the bright part); dark_spot is judged RELATIVE
    to the on-part median (clearly darker than the finish), so a faint real spot is not
    dropped, while a box fabricated on plain grain/tint - which is NOT darker than the
    finish - is still rejected. part_ref = median brightness of the on-part metal."""
    if cv2 is None:
        return True  # can't verify without cv2; don't drop
    x0, y0, x1, y1 = _bbox_px(bbox, W, H)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return False
    roi = base[y0:y1, x0:x1]
    gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
    dark_abs = _dark_abs(part_ref, category)
    mask = (gray < dark_abs).astype(np.uint8)

    # A dark_spot may be a single meaningful spot or a localized cluster of
    # several small spots. Require coherent dark content and local contrast, but
    # do not require one large connected component.
    if str(category or "").lower() == "dark_spot":
        n, labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, 8)
        if n <= 1:
            return False
        areas = stats[1:, cv2.CC_STAT_AREA]
        min_component = max(3, int(0.0008 * mask.size))
        keep = np.zeros_like(mask, dtype=np.uint8)
        for label, area in enumerate(areas, start=1):
            if int(area) >= min_component:
                keep[labels == label] = 1
        meaningful_area = int(keep.sum())
        if meaningful_area < max(8, int(0.003 * mask.size)):
            return False

        core = gray[keep > 0]
        ring_mask = cv2.dilate(keep, np.ones((5, 5), np.uint8), iterations=1)
        ring = (ring_mask > 0) & (keep == 0)
        if not np.any(ring) or core.size == 0:
            return False
        local_contrast = float(np.median(gray[ring])) - float(np.median(core))
        if local_contrast < 8.0:
            return False

    return float(mask.mean()) >= _DARK_MIN_CONTENT


def _tighten_dark_bbox(base, bbox, part_ref, W, H, margin=0.006, category=None):
    """Shrink a (possibly loose) dark_* box to the LARGEST darker-than-finish blob inside
    it, so the drawn box hugs the actual dark pixels instead of the surrounding tint.
    Returns the original bbox when no clean blob is found."""
    if cv2 is None:
        return list(bbox)
    x0, y0, x1, y1 = _bbox_px(bbox, W, H)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return list(bbox)
    roi = base[y0:y1, x0:x1]
    gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
    dark_abs = _dark_abs(part_ref, category)
    mask = (gray < dark_abs).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, _lbl, stats, _c = cv2.connectedComponentsWithStats(mask)
    if n <= 1:
        return list(bbox)
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    cx, cy, cw, ch, area = stats[i]
    if area < 6:
        return list(bbox)
    pad = int(margin * max(W, H))
    mx0 = max(0, x0 + int(cx) - pad)
    my0 = max(0, y0 + int(cy) - pad)
    mx1 = min(W, x0 + int(cx) + int(cw) + pad)
    my1 = min(H, y0 + int(cy) + int(ch) + pad)
    bw, bh = (mx1 - mx0) / W, (my1 - my0) / H
    # Floor the hugged box so a faint small spot is not shrunk below the actionable /
    # visible size and then dropped by the sub-actionable speck gate (the edge/scatter
    # dark_spot miss). Expand around the blob centre, keeping it on-image.
    floor = 0.028
    cxn = (mx0 + (mx1 - mx0) / 2.0) / W
    cyn = (my0 + (my1 - my0) / 2.0) / H
    bw, bh = max(bw, floor), max(bh, floor)
    nx = min(max(0.0, cxn - bw / 2.0), 1.0 - bw)
    ny = min(max(0.0, cyn - bh / 2.0), 1.0 - bh)
    return [nx, ny, bw, bh]


def _part_mask_full(base, W, H):
    """Solid binary part-silhouette mask (uint8 0/255) for the whole image, via a
    local-texture (std) map + the largest non-background component, filled solid so
    smooth interior metal still counts as on-part. None if cv2 missing / unreliable.
    Used only to REJECT a defect box that falls off the part onto the background."""
    if cv2 is None:
        return None
    try:
        scale = min(1.0, 360.0 / float(max(H, W)))
        sm = (cv2.resize(base, (max(8, int(W * scale)), max(8, int(H * scale))),
                         interpolation=cv2.INTER_AREA) if scale < 1.0 else base)
        g = cv2.cvtColor(sm, cv2.COLOR_RGB2GRAY).astype(np.float32)
        win = max(7, (int(min(sm.shape[0], sm.shape[1]) * 0.04) | 1))
        mean = cv2.boxFilter(g, -1, (win, win))
        sq = cv2.boxFilter(g * g, -1, (win, win))
        std = np.clip(np.sqrt(np.clip(sq - mean * mean, 0, None)), 0, 255).astype(np.uint8)
        _, mask = cv2.threshold(std, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        k = max(3, (int(min(sm.shape[0], sm.shape[1]) * 0.03) | 1))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8), iterations=2)
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            return None
        solid = np.zeros_like(mask)
        cv2.drawContours(solid, [max(cnts, key=cv2.contourArea)], -1, 255, -1)
        if scale < 1.0:
            solid = cv2.resize(solid, (W, H), interpolation=cv2.INTER_NEAREST)
        return solid
    except Exception:
        return None


def _box_gap(a, b):
    """Normalized edge-to-edge gap between two [x,y,w,h] boxes (0 if overlapping)."""
    ax1, ay1 = a[0] + a[2], a[1] + a[3]
    bx1, by1 = b[0] + b[2], b[1] + b[3]
    dx = max(0.0, b[0] - ax1, a[0] - bx1)
    dy = max(0.0, b[1] - ay1, a[1] - by1)
    return max(dx, dy)


def _box_union(a, b):
    x0, y0 = min(a[0], b[0]), min(a[1], b[1])
    x1, y1 = max(a[0] + a[2], b[0] + b[2]), max(a[1] + a[3], b[1] + b[3])
    return [x0, y0, x1 - x0, y1 - y0]


def _merge_same_category(defects):
    """Collapse same-category region boxes whose gap is <= _MERGE_GAP into one union
    box (the user rule: tiny space between boxes -> a single box). Line defects and
    boxless defects pass through untouched."""
    items = [[list(map(float, d["bbox"])) if isinstance(d.get("bbox"), (list, tuple))
              and len(d.get("bbox")) == 4 else None, d] for d in defects]
    changed = True
    while changed:
        changed = False
        for i in range(len(items)):
            bi, di = items[i]
            if bi is None:
                continue
            for j in range(i + 1, len(items)):
                bj, dj = items[j]
                if bj is None:
                    continue
                if str(di.get("category", "")).lower() != str(dj.get("category", "")).lower():
                    continue
                if _box_gap(bi, bj) <= _MERGE_GAP:
                    union = _box_union(bi, bj)
                    nd = dict(di)
                    nd["bbox"] = union
                    nd["severity"] = max(di.get("severity", 0) or 0, dj.get("severity", 0) or 0)
                    nd["confidence"] = max(di.get("confidence", 0) or 0, dj.get("confidence", 0) or 0)
                    nd["_merged"] = True
                    items[i] = [union, nd]
                    items.pop(j)
                    changed = True
                    break
            if changed:
                break
    return [d for _b, d in items]


def _clip_bbox_to_part(bbox, part_mask, W, H):
    """Keep the reported rectangle on the detected part without tightening to pixels.

    This changes only the portion that would extend beyond the part silhouette; it
    does not search for or shrink the box around the defect itself.
    """
    if part_mask is None or cv2 is None:
        return list(bbox)
    x, y, w, h = [float(v) for v in bbox]
    x0, y0, x1, y1 = x, y, x + w, y + h
    px0, py0, px1, py1 = _bbox_px([x0, y0, max(0.0, w), max(0.0, h)], W, H)
    if px1 <= px0 or py1 <= py0:
        return list(bbox)
    # Trim only the portion that lies outside the part silhouette. We do
    # not tighten around defect pixels. The final rectangle must be entirely
    # inside the solid outer-part silhouette.
    max_steps = max(1, (px1 - px0) + (py1 - py0))
    for _ in range(max_steps):
        sub = part_mask[py0:py1, px0:px1]
        if sub.size == 0 or bool(np.all(sub > 0)):
            break
        candidates = []
        if py1 - py0 > 2:
            candidates.append(("top", int(np.count_nonzero(sub[0] == 0))))
            candidates.append(("bottom", int(np.count_nonzero(sub[-1] == 0))))
        if px1 - px0 > 2:
            candidates.append(("left", int(np.count_nonzero(sub[:, 0] == 0))))
            candidates.append(("right", int(np.count_nonzero(sub[:, -1] == 0))))
        if not candidates:
            break
        side, score = max(candidates, key=lambda item: item[1])
        if score <= 0:
            # Background remains only in the interior; remove the side with
            # the largest total background count until the rectangle is valid.
            candidates = [
                ("top", int(np.count_nonzero(sub[0] == 0))),
                ("bottom", int(np.count_nonzero(sub[-1] == 0))),
                ("left", int(np.count_nonzero(sub[:, 0] == 0))),
                ("right", int(np.count_nonzero(sub[:, -1] == 0))),
            ]
            side, score = max(candidates, key=lambda item: item[1])
            if score <= 0:
                break
        if side == "top":
            py0 += 1
        elif side == "bottom":
            py1 -= 1
        elif side == "left":
            px0 += 1
        else:
            px1 -= 1
    # Convert the boundary-clipped pixel rectangle back to normalized coordinates.
    nx0, ny0 = px0 / float(W), py0 / float(H)
    nx1, ny1 = px1 / float(W), py1 / float(H)
    return [nx0, ny0, max(0.0, nx1 - nx0), max(0.0, ny1 - ny0)]



def _sanitize_region_defects(defects, part_mask, base, W, H):
    """Safety net applied before drawing (also catches an API hallucination):
      1. DROP a box that falls off the part (on background / empty space).
      2. DROP a dark_* box with no genuine near-black content (fabricated on grain/tint).
      3. MERGE same-category boxes separated by only a tiny gap into ONE box.
      4. DROP a lone sub-actionable speck (below the actionability area gate).
    Line defects pass through untouched. Returns (kept_defects, changed)."""
    lines = []
    boxes = list(defects)
    changed = False
    clipped_lines = []
    for d in lines:
        if isinstance(d.get("bbox"), (list, tuple)) and len(d.get("bbox")) == 4 and part_mask is not None:
            clipped = _clip_bbox_to_part(d["bbox"], part_mask, W, H)
            if [round(v, 6) for v in clipped] != [round(float(v), 6) for v in d["bbox"]]:
                d = dict(d)
                d["bbox"] = clipped
                changed = True
        clipped_lines.append(d)
    lines = clipped_lines
    part_ref = 180.0
    if part_mask is not None and cv2 is not None:
        on = cv2.cvtColor(base, cv2.COLOR_RGB2GRAY)[part_mask > 0]
        if on.size:
            part_ref = float(np.median(on))
    # 1. off-part guard + 2. dark-content guard
    on_part = []
    for d in boxes:
        bb = d.get("bbox")
        if isinstance(bb, (list, tuple)) and len(bb) == 4:
            if part_mask is not None:
                x0, y0, x1, y1 = _bbox_px(bb, W, H)
                if x1 > x0 and y1 > y0:
                    sub = part_mask[y0:y1, x0:x1]
                    if sub.size and float((sub > 0).mean()) < _OFFPART_MIN_OVERLAP:
                        changed = True
                        continue
            # Dark-feature semantics are owned by grounding + model inspection.
            # The renderer only constrains reported boxes to the detected part silhouette.
        # Keep region boxes on the part, but do not tighten them to defect pixels.
        if isinstance(d.get("bbox"), (list, tuple)) and len(d.get("bbox")) == 4 and part_mask is not None:
            clipped = _clip_bbox_to_part(d["bbox"], part_mask, W, H)
            if [round(v, 6) for v in clipped] != [round(float(v), 6) for v in d["bbox"]]:
                d = dict(d)
                d["bbox"] = clipped
                changed = True
        on_part.append(d)
    # 3. merge same-category near boxes
    merged = _merge_same_category(on_part)
    if len(merged) != len(on_part):
        changed = True
    # 3. drop only generic sub-actionable region boxes. Dark spots are
    # intentionally exempt because their semantic actionability is a grounding
    # decision, not a renderer decision.
    final = []
    for d in merged:
        bb = d.get("bbox")
        if (str(d.get("category", "")).lower() != "dark_spot"
                and not d.get("_merged")
                and isinstance(bb, (list, tuple)) and len(bb) == 4
                and bb[2] * bb[3] < _MIN_ACTIONABLE_AREA):
            changed = True
            continue
        d.pop("_merged", None)
        final.append(d)
    return final, changed


def render_annotated(image_path: str, verdict: dict, out_path: Optional[str] = None) -> str:
    out_path = out_path or os.path.join(os.path.dirname(image_path), "annotated.png")
    img = Image.open(image_path)
    img = ImageOps.exif_transpose(img).convert("RGB")  # honor camera orientation
    W, H = img.size
    colors = _catalog_colors()
    fscale = max(14, int(min(W, H) * 0.028))
    font = _font(fscale)

    # Collect defect regions. Category-specific segmentation is applied during drawing.
    instances = verdict.get("instances")
    if isinstance(instances, list):
        order = {"DEFECT": 0, "NEEDS_REVIEW": 1, "OK": 2}
        results = [i.get("result", "NEEDS_REVIEW") for i in instances]
        result = min(results, key=lambda r: order.get(r, 3)) if results else "NEEDS_REVIEW"
        groups = [inst.get("defects", []) for inst in instances]
    else:
        result = verdict.get("result", "NEEDS_REVIEW")
        instances = None
        groups = [verdict.get("defects", [])]

    # --- Phase 1: segmentation fills + outlines on a numpy array (cv2) ---------
    arr = np.ascontiguousarray(np.array(img))  # RGB uint8
    base = arr.copy()  # clean pixels for part-silhouette tightening
    # Safety-net verdict cleanup (also catches an API hallucination): drop off-part
    # boxes, merge same-category near boxes, drop lone sub-actionable specks. If a
    # group's boxes are ALL dropped, don't silently pass it - downgrade to review.
    part_mask = _part_mask_full(base, W, H)
    cleaned = []
    for defs in groups:
        had_boxes = bool(defs)
        kept, changed = _sanitize_region_defects(defs, part_mask, base, W, H)
        if changed and had_boxes and not kept \
                and result == "DEFECT":
            result = "NEEDS_REVIEW"
        cleaned.append(kept)
    groups = cleaned
    label_jobs = []  # (anchor, label, col, font)
    # primary = highest-severity defect within each group
    group_primary = [max(defs, key=lambda d: d.get("severity", 0), default=None)
                     for defs in groups]
    # per-instance tight part box (px): shrink a loose instance_bbox to the actual
    # part silhouette so the frame hugs the part and marks scale to it. None when
    # single-part / no instance / the part fills the frame (no frame drawn).
    inst_list = instances if instances is not None else [None] * len(groups)
    inst_boxes = []
    for inst in inst_list:
        if inst is None:
            inst_boxes.append(None)
            continue
        bb = inst.get("instance_bbox")
        if not (isinstance(bb, list) and len(bb) == 4):
            inst_boxes.append(None)
            continue
        x, y, w, h = bb
        if w >= 0.9 and h >= 0.9:  # part fills the photo -> no sub-region frame
            inst_boxes.append(None)
            continue
        px = (int(x * W), int(y * H), int((x + w) * W), int((y + h) * H))
        inst_boxes.append(_tighten_to_part(base, px))
    # mark styling scaled to the tightened part box (fallback to instance style)
    group_style = []
    for gi in range(len(groups)):
        if inst_boxes[gi] is not None:
            bx0, by0, bx1, by1 = inst_boxes[gi]
            side = max(1.0, min(bx1 - bx0, by1 - by0))
            group_style.append(_instance_style_side(side, W, H))
        else:
            group_style.append(_instance_style(inst_list[gi], W, H))
    if cv2 is not None:
        # multiple parts in this one image -> thin bounding boxes only; a single
        # part -> full QMS inner marking (contour + fill) + box.
        multi_part = instances is not None and len(instances) > 1
        overlay = arr.copy()
        for gi, defects in enumerate(groups):
            fnt, thick, _scale = group_style[gi]
            for d in defects:
                job = _fill_and_outline(arr, overlay, d, W, H, colors,
                                        d is group_primary[gi], thick,
                                        multi_part=multi_part)
                if job:
                    anchor, label, col, rrect = job
                    label_jobs.append((anchor, label, col, fnt, rrect))
        cv2.addWeighted(overlay, _FILL_ALPHA, arr, 1 - _FILL_ALPHA, 0, arr)
        img = Image.fromarray(arr)

    draw = ImageDraw.Draw(img)

    # --- Phase 2: PIL labels and instance frames --------------------
    # Draw instance name chips FIRST and record their rects, so region/line defect
    # labels drawn afterwards can dodge them and never get painted over (the cup's
    # "Edge Chip" category label used to hide behind the "Bearing Cup" name chip).
    occupied = []
    for gi in range(len(groups)):
        fnt, _thick, _scale = group_style[gi]
        if instances is not None and inst_boxes[gi] is not None:
            rect = _draw_instance_frame(draw, instances[gi], inst_boxes[gi], W, H, fnt)
            if rect:
                occupied.append(rect)

    if cv2 is not None:
        # Every defect region is a keep-clear zone: seed occupied with ALL defect
        # rects first so no label is painted over a mark (its own or a neighbour's).
        for _a, _l, _c, _f, rrect in label_jobs:
            occupied.append(rrect)
        for anchor, label, col, fnt, _rrect in label_jobs:
            _draw_label(draw, anchor, label, col, fnt, W, H, occupied)

    # All configured defects are region annotations; category-specific segmentation
    # is handled by _SEG_BY_CATEGORY above.
    if cv2 is None:
        for gi, defects in enumerate(groups):
            fnt, _thick, _scale = group_style[gi]
            for d in defects:
                _fallback_box(draw, d, W, H, colors, fnt)

    # QMS marks a clean part with a green border + banner (defect frames carry no
    # extra chrome - only the defect marks/labels themselves).
    if result == "OK":
        gcol = _STATUS_COLOR["OK"]
        draw.rectangle([0, 0, W - 1, H - 1], outline=gcol, width=max(6, int(min(W, H) * 0.01)))
        rf = _font(max(14, int(min(W, H) * 0.03)))
        label = "OK - no defect"
        tw, th = _text_size(draw, label, rf)
        draw.rectangle([8, 8, 8 + tw + 16, 8 + th + 12], fill=gcol)
        draw.text((16, 14), label, fill=(255, 255, 255), font=rf)

    img.save(out_path)
    return out_path


def _fallback_box(draw, d, W, H, colors, font):
    """Plain box + label used only when cv2 is unavailable (no fill/segmentation)."""
    bbox = d.get("bbox") or [0, 0, 0, 0]
    if len(bbox) != 4:
        return
    col = colors.get(str(d.get("category", "")).lower(), (245, 158, 11))
    x0, y0, x1, y1 = _bbox_px(bbox, W, H)
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    for pad, c, wd in ((2, (10, 15, 25), 6), (0, col, 3)):
        draw.rectangle([x0 - pad, y0 - pad, x1 + pad, y1 + pad], outline=c, width=wd)
    _draw_label(draw, (x0, y0), _defect_label(d, False), col, font, W, H)
