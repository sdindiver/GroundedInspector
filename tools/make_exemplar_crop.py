"""Generate a tight localization CROP (and optional caption sidecar) for a defect exemplar.

Policy: every defect exemplar = the FULL part image + a tight CROP of the defect, so the
vision API is shown both the context and exactly WHERE the defect is. This writes
`<stem>_crop.png` next to the exemplar (the assembler/inspect pair it with the full image),
and optionally a `<stem>.txt` one-line locator caption.

The crop bbox is authored BY LOOKING at the defect (normalized 0..1, display orientation) -
never guessed. Usage:

  python -m tools.make_exemplar_crop --image grounding/references/global/white_mark/IMG..png \
         --bbox 0.34 0.14 0.30 0.24 --pad 0.12 \
         --caption "white_mark = dull low-luster patch above the middle hole; grain still visible, not glare"
"""
from __future__ import annotations

import argparse
import os

from PIL import Image, ImageOps


def make_crop(image_path: str, bbox, pad: float = 0.12, out_path: str | None = None) -> str:
    img = ImageOps.exif_transpose(Image.open(image_path)).convert("RGB")
    W, H = img.size
    x, y, w, h = bbox
    px, py = pad * w, pad * h
    x0 = max(0, int(round((x - px) * W)))
    y0 = max(0, int(round((y - py) * H)))
    x1 = min(W, int(round((x + w + px) * W)))
    y1 = min(H, int(round((y + h + py) * H)))
    if x1 <= x0 or y1 <= y0:
        raise ValueError(f"empty crop for bbox {bbox} on {W}x{H} image")
    stem, _ = os.path.splitext(image_path)
    out_path = out_path or f"{stem}_crop.png"
    img.crop((x0, y0, x1, y1)).save(out_path)
    return out_path


def _write_caption(image_path: str, caption: str) -> str:
    stem, _ = os.path.splitext(image_path)
    side = f"{stem}.txt"
    with open(side, "w", encoding="utf-8") as fh:
        fh.write(caption.strip() + "\n")
    return side


def main() -> None:
    ap = argparse.ArgumentParser(description="Make a tight localization crop for a defect exemplar.")
    ap.add_argument("--image", required=True, help="path to the full exemplar image")
    ap.add_argument("--bbox", required=True, nargs=4, type=float, metavar=("X", "Y", "W", "H"),
                    help="normalized 0..1 defect box (display orientation)")
    ap.add_argument("--pad", type=float, default=0.12, help="fractional context padding around the box")
    ap.add_argument("--caption", default=None, help="one-line locator caption -> <stem>.txt sidecar")
    ap.add_argument("--out", default=None, help="explicit crop output path (default <stem>_crop.png)")
    args = ap.parse_args()

    crop = make_crop(args.image, args.bbox, args.pad, args.out)
    print(f"crop -> {crop}")
    if args.caption:
        print(f"caption -> {_write_caption(args.image, args.caption)}")


if __name__ == "__main__":
    main()
