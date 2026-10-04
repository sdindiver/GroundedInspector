"""Run a grounded inspection the PRODUCTION way, end to end:

    grounding bundle + raw image  ->  Anthropic Vision API  ->  verdict  ->  annotated image

This is the missing ENGINE. It stores NO verdict and hardcodes NO path: the verdict is
produced fresh by the API from the bundle (grounding/) + the image every run, so the same
project handed to a colleague produces the SAME result (temperature=0 => deterministic).
The only durable knowledge is the bundle; this module just drives it.

Setup (once):
    pip install -r requirements.txt          # includes the anthropic SDK
    setx ANTHROPIC_API_KEY "sk-ant-..."      # colleague supplies their own key
    setx ANTHROPIC_MODEL   "claude-...."     # a vision-capable model snapshot (pin for reproducibility)

Run (paths are given at RUN TIME, never baked in):
    python -m grounded_inspector.inspect --part bracket --folder "C:/path/to/images"
    python -m grounded_inspector.inspect --part bracket --image  "C:/path/to/one.png"
    python -m grounded_inspector.inspect --auto            --image  "C:/path/to/photo.png"

Output: <folder>/annotated/<stem>_ANNOTATED.png (folder mode) or <image dir>/annotated/... .
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
from typing import List, Optional, Tuple

from . import assembler
from . import grid
from . import loader as C

_EXTS = (".png", ".jpg", ".jpeg", ".PNG", ".JPG", ".JPEG")
_MEDIA = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
_DEFECT, _REVIEW, _OK = "DEFECT", "NEEDS_REVIEW", "OK"

DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")


# --------------------------------------------------------------- bundle -> verdict meta
def _catalog_meta() -> dict:
    """category(lower) -> {severity, display_name}, read from the bundle so those are
    resolved from grounding, never carried in the model's JSON or typed in a script."""
    meta: dict = {}
    for name, spec in (C.load_global_catalog().get("defects", {}) or {}).items():
        meta[name.lower()] = {
            "severity": spec.get("severity", 2),
            "display_name": spec.get("display_name", name.replace("_", " ").title()),
        }
    for part in C.list_parts():
        for name, spec in (part.get("defects", {}) or {}).items():
            meta[name.lower()] = {
                "severity": spec.get("severity", 3),
                "display_name": spec.get("display_name", name.replace("_", " ").title()),
            }
    return meta


def build_verdict(raw: dict, meta: dict) -> dict:
    """Normalize the engine verdict without dropping fields required by the output contract.

    Grounding resolves catalog metadata (severity/display_name), while the model's
    evidence fields (reason, location, lines, checkpoints, review reason, etc.) are
    preserved so the renderer and callers see the complete verdict.
    """
    defects = []
    top = 0.0
    for d in raw.get("defects", []) or []:
        cat = str(d.get("category", "")).lower()
        if not cat or "bbox" not in d:
            continue
        m = meta.get(cat, {"severity": 2, "display_name": cat.replace("_", " ").title()})
        factors = d.get("confidence_factors") or d.get("factors")
        if factors:
            try:
                conf = confidence.score(cat, factors)[0]
            except ValueError:
                conf = float(d.get("confidence", 0.0) or 0.0)
        elif "confidence" in d and d["confidence"] is not None:
            conf = float(d["confidence"])
        else:
            conf = 0.0
        top = max(top, conf)
        item = {
            "category": cat,
            "scope": d.get("scope", "part" if cat in meta else "global"),
            "severity": m["severity"],
            "bbox": list(d["bbox"]),
            "confidence": round(conf, 2),
            "reason": d.get("reason", ""),
            "display_name": m["display_name"],
        }
        for key in ("line", "lines", "location"):
            if key in d:
                item[key] = d[key]
        defects.append(item)

    result = raw.get("result")
    if result not in (_DEFECT, _REVIEW, _OK):
        result = _OK if not defects else (_DEFECT if top >= 0.60 else _REVIEW)

    verdict = {
        "part": raw.get("part"),
        "image": raw.get("image"),
        "result": result,
        "primary": raw.get("primary"),
        "needs_review_reason": raw.get("needs_review_reason"),
        "checkpoints": raw.get("checkpoints", []) or [],
        "defects": defects,
    }
    return verdict


# ------------------------------------------------------------------- API engine call
def _encode_image(path: str) -> dict:
    ext = os.path.splitext(path)[1].lower()
    with open(path, "rb") as fh:
        image_data = fh.read()
    from PIL import Image
    with Image.open(io.BytesIO(image_data)) as image:
        if max(image.size) > 2000:
            image.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="PNG" if ext == ".png" else "JPEG", quality=95)
            image_data = output.getvalue()
    data = base64.standard_b64encode(image_data).decode("ascii")
    return {"type": "image", "source": {"type": "base64",
            "media_type": _MEDIA.get(ext, "image/png"), "data": data}}


def _bundle_images(bundle: dict) -> List[Tuple[str, str]]:
    """(label, path) for every image the prompt references, input LAST (as the prompt says).
    Each defect example is attached as the FULL part image plus its tight LOCALIZED CROP
    (context + where-it-is), so the API is shown exactly where a subtle defect sits."""
    imgs: List[Tuple[str, str]] = []
    for g in bundle.get("golden_images", []):
        imgs.append(("GOLDEN reference", g))
    for d in bundle.get("defects", []):
        cat = d["category"]
        for pair in C.pair_exemplars(d.get("reference_images", [])):
            cap = f" - {pair['caption']}" if pair.get("caption") else ""
            if pair["full"]:
                imgs.append((f"DEFECT exemplar ({cat}) FULL part{cap}", pair["full"]))
            if pair["crop"]:
                imgs.append((f"DEFECT exemplar ({cat}) LOCALIZED CROP - the defect is HERE", pair["crop"]))
    # Attach a coordinate-grid copy of the input so the engine READS each bbox edge off
    # the labeled gridlines instead of estimating a fraction (tighter localization). The
    # clean input is attached LAST (as the prompt says) for judging the defect itself.
    grid_path = grid.grid_for(bundle["image"])
    if grid_path:
        imgs.append(("INPUT with COORDINATE GRID - read each bbox edge off the nearest "
                     "labeled gridline (0.00-1.00 across the top = x, down the left = y)", grid_path))
    imgs.append(("INPUT to inspect", bundle["image"]))
    return [(lbl, p) for lbl, p in imgs if p and os.path.isfile(p)]


def call_engine(prompt_text: str, images: List[Tuple[str, str]], model: str) -> dict:
    """Send the assembled bundle prompt + attached images to the Anthropic Vision API and
    return the parsed verdict JSON. Sampling parameters are omitted because current
    adaptive-thinking models reject temperature/top_p/top_k. Requires the `anthropic`
    SDK and ANTHROPIC_API_KEY in the environment (the colleague's own key)."""
    try:
        import truststore
        truststore.inject_into_ssl()
        import anthropic
    except ImportError as e:  # noqa
        raise RuntimeError("The API dependencies are not installed. Run: pip install -r requirements.txt") from e
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Set it to your Anthropic API key and re-run.")

    content: List[dict] = [{"type": "text", "text": prompt_text}]
    for label, path in images:
        content.append({"type": "text", "text": f"[{label}]"})
        content.append(_encode_image(path))

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=model, max_tokens=3000,
        messages=[{"role": "user", "content": content}],
    )
    text = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text")
    return _parse_verdict_json(text)


def _parse_verdict_json(text: str) -> dict:
    """Extract the JSON object from the model reply (tolerating ```json fences / prose)."""
    t = text.strip()
    if "```" in t:
        t = t.split("```", 2)[1]
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found in engine reply:\n{text[:400]}")
    return json.loads(t[start:end + 1])


# --------------------------------------------------------------------------- pipeline
def inspect_image(part: Optional[str], image_path: str, model: str, meta: dict) -> dict:
    """Assemble the bundle for (part, image), call the engine, return the full verdict."""
    if part:
        bundle = assembler.build_bundle(part, image_path)
    else:
        bundle = assembler.build_auto_bundle(image_path)
    prompt = assembler.render_prompt(bundle) if part else assembler.render_auto_prompt(bundle)
    raw = call_engine(prompt, _bundle_images(bundle), model)
    return build_verdict(raw, meta)


def _iter_images(folder: str) -> List[str]:
    out = [os.path.join(folder, f) for f in os.listdir(folder)
           if os.path.splitext(f)[1] in _EXTS]
    return sorted(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--part", help="part name (e.g. bracket); omit with --auto")
    g.add_argument("--auto", action="store_true", help="auto-identify the part, then inspect")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--image", help="single input image path")
    src.add_argument("--folder", help="folder of input images")
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"vision model (default {DEFAULT_MODEL})")
    ap.add_argument("--out", help="output path (single-image mode only)")
    args = ap.parse_args(argv)

    from . import renderer  # deferred so --help works without PIL/cv2
    meta = _catalog_meta()
    part = None if args.auto else args.part

    targets = [args.image] if args.image else _iter_images(args.folder)
    if not targets:
        ap.error("no images found to inspect")
    out_dir = os.path.join(args.folder, "annotated") if args.folder else \
        (os.path.dirname(args.out) if args.out else os.path.join(os.path.dirname(args.image) or ".", "annotated"))
    os.makedirs(out_dir, exist_ok=True)

    n = 0
    for src_path in targets:
        stem = os.path.splitext(os.path.basename(src_path))[0]
        verdict = inspect_image(part, src_path, args.model, meta)
        out = args.out if (args.image and args.out) else os.path.join(out_dir, f"{stem}_ANNOTATED.png")
        renderer.render_annotated(src_path, verdict, out)
        cats = ", ".join(sorted({d["category"] for d in verdict["defects"]})) or "-"
        print(f"{verdict['result']:<12} {stem}  [{cats}]")
        n += 1
    print(f"Inspected {n} image(s); annotated -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
