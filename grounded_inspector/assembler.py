"""Assemble a grounding bundle for one (part, image) inspection.

A bundle is everything a vision model needs to produce a grounded verdict:
  - the system prompt
  - the resolved defect catalog (global + part-specific) as readable text
  - the list of golden reference images
  - the list of per-defect reference (few-shot) images
  - the target input image

It renders both a human/model-readable prompt.md and a machine manifest.json so
the same bundle can be consumed by the IDE model today or the Anthropic API later.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Dict, List

from . import loader as C

ROOT = C.ROOT
GROUNDING_DIR = os.path.join(ROOT, "grounding")
RUNS_DIR = os.path.join(ROOT, "runs")

AUTO = "__auto__"


def is_auto(part_name: str) -> bool:
    return (part_name or "").strip().lower() in (AUTO, "auto", "", "auto-detect", "auto_detect")


def _system_prompt() -> str:
    with open(os.path.join(GROUNDING_DIR, "system_prompt.md"), "r", encoding="utf-8") as fh:
        return fh.read()


def _rel(path: str) -> str:
    try:
        return os.path.relpath(path, ROOT)
    except ValueError:
        return path


def build_bundle(part_name: str, image_path: str) -> dict:
    part = C.load_part(part_name)
    catalog = C.load_global_catalog()
    defects = C.resolve_defects(part, catalog)
    golden = C.golden_images(part)

    return {
        "part": part.get("part", part_name),
        "part_description": part.get("description", ""),
        "identity": part.get("identity", {}) or {},
        "image": os.path.abspath(image_path),
        "rulings": C.resolve_ref_list(part.get("rulings", [])),
        "notes": C.resolve_ref_list(part.get("notes", [])),
        "golden_images": golden,
        "defects": defects,
        "warnings": _warnings(golden, defects, image_path),
    }


def _warnings(golden: List[str], defects: List[dict], image_path: str) -> List[str]:
    w = []
    if not golden:
        w.append("No golden reference image found - grounding is weaker. Drop a clean "
                 "image into the part's references/.../golden folder.")
    if not os.path.isfile(image_path):
        w.append(f"Input image not found on disk: {image_path}")
    for d in defects:
        if d["scope"] == "part" and not d["reference_images"]:
            w.append(f"Part defect '{d['category']}' has no reference images - add exemplars "
                     f"for stronger few-shot grounding.")
    return w


def _label(key: str) -> str:
    return key.replace("_", " ").upper()


def _prose(v):
    """Render a prose value: a plain string as-is, OR a list of sentences joined with a
    single space (authoring sugar so a long rule can be written as a diff-able sentence list
    that renders to the IDENTICAL string). Dicts (e.g. confidence_model) render to nothing,
    exactly as before - they are consumed by code, not the prompt."""
    if isinstance(v, str):
        return v
    if isinstance(v, (list, tuple)):
        return " ".join(str(x) for x in v)
    return None


def _defect_lines(d: dict, indent: str = "    ") -> List[str]:
    """Render every grounding field of a resolved defect so the prompt is
    self-contained (signature + annotation + all guidance: disambiguation,
    glare_rule, ...). Nothing grounding-relevant is left out of the bundle."""
    out: List[str] = []
    ann = d.get("annotation")
    if ann and ann.get("instruction"):
        out.append(f"{indent}ANNOTATION [{ann.get('shape', 'box')}]: {ann['instruction']}")
    for k, v in (d.get("guidance") or {}).items():
        text = _prose(v)
        if text and text.strip():
            out.append(f"{indent}{_label(k)}: {text}")
    return out


def render_prompt(bundle: dict) -> str:
    lines: List[str] = []
    lines.append(_system_prompt())
    lines.append("\n---\n")
    lines.append(f"# PART: {bundle['part']}")
    if bundle["part_description"]:
        lines.append(bundle["part_description"])
    idn = bundle.get("identity") or {}
    if idn.get("summary"):
        lines.append(f"IDENTITY / ANATOMY: {idn['summary']}")
    if idn.get("distinguishing_features"):
        lines.append("Anatomy anchors: " + "; ".join(idn["distinguishing_features"]))
    lines.append("")
    lines.append("## DEFECT CATALOG (only these categories may be reported)")
    for d in bundle["defects"]:
        lines.append(f"- **{d['category']}** [{d['scope']}, severity {d['severity']}]: "
                     f"{d['signature']}")
        lines.extend(_defect_lines(d))
    lines.append("")
    if bundle["rulings"]:
        lines.append("## RULINGS")
        for r in bundle["rulings"]:
            lines.append(f"- {_prose(r)}")
        lines.append("")
    if bundle["notes"]:
        lines.append("## NOTES")
        for n in bundle["notes"]:
            lines.append(f"- {_prose(n)}")
        lines.append("")
    lines.append("## IMAGES ATTACHED")
    for g in bundle["golden_images"]:
        lines.append(f"- GOLDEN reference: {_rel(g)}")
    for d in bundle["defects"]:
        for pair in C.pair_exemplars(d["reference_images"]):
            cap = f" - {pair['caption']}" if pair.get("caption") else ""
            if pair["full"]:
                lines.append(f"- DEFECT exemplar ({d['category']}) FULL part: {_rel(pair['full'])}{cap}")
            if pair["crop"]:
                lines.append(f"    -> LOCALIZED CROP of that same {d['category']} (the defect "
                             f"zoomed in - THIS shows exactly where it is): {_rel(pair['crop'])}")
    lines.append(f"- INPUT to inspect: {_rel(bundle['image'])}")
    lines.append("")
    if bundle["warnings"]:
        lines.append("## GROUNDING WARNINGS")
        for warn in bundle["warnings"]:
            lines.append(f"- {warn}")
        lines.append("")
    lines.append("Now inspect the INPUT image and return the JSON verdict only.")
    return "\n".join(lines)


def write_bundle(part_name: str, image_path: str, run_dir: str = None) -> str:
    bundle = build_bundle(part_name, image_path)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = os.path.splitext(os.path.basename(image_path))[0]
    run_dir = run_dir or os.path.join(RUNS_DIR, f"{ts}_{stem}")
    os.makedirs(run_dir, exist_ok=True)

    manifest = {
        "part": bundle["part"],
        "mode": "single",
        "image": bundle["image"],
        "golden_images": bundle["golden_images"],
        "reference_images": {
            d["category"]: d["reference_images"] for d in bundle["defects"]
        },
        "defects": [
            {k: d[k] for k in ("category", "scope", "severity")} for d in bundle["defects"]
        ],
        "warnings": bundle["warnings"],
    }
    with open(os.path.join(run_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    with open(os.path.join(run_dir, "prompt.md"), "w", encoding="utf-8") as fh:
        fh.write(render_prompt(bundle))
    return run_dir


# ----------------------------------------------------- auto identify + inspect ----
def build_auto_bundle(image_path: str) -> dict:
    """Bundle for identify-then-inspect: no part is pre-selected.

    Gives the engine every known part's identity signature (+ a golden thumbnail)
    and every part's resolved defect catalog, so it can (1) find each part present
    in the image, (2) identify it, then (3) inspect each with the right rules.
    """
    catalog = C.load_global_catalog()
    registry = C.part_identities(max_golden=1)
    parts = []
    for entry in registry:
        cfg = C.load_part(entry["part"])
        defects = C.resolve_defects(cfg, catalog)
        parts.append({
            "part": entry["part"],
            "aliases": entry["aliases"],
            "description": entry["description"],
            "identity": entry["identity"],
            "golden_images": entry["golden_images"],
            "rulings": C.resolve_ref_list(cfg.get("rulings", [])),
            "notes": C.resolve_ref_list(cfg.get("notes", [])),
            "defects": defects,
        })
    warnings = []
    if not os.path.isfile(image_path):
        warnings.append(f"Input image not found on disk: {image_path}")
    if not parts:
        warnings.append("No parts are configured - add at least one config/parts/*.json.")
    return {
        "mode": "auto",
        "image": os.path.abspath(image_path),
        "parts": parts,
        "warnings": warnings,
        "crops": [],
    }


def render_auto_prompt(bundle: dict) -> str:
    crops = bundle.get("crops") or []
    multi = len(crops) >= 2
    lines: List[str] = [_system_prompt(), "\n---\n"]
    lines.append("# MODE: AUTO-IDENTIFY THEN INSPECT")
    if multi:
        lines.append(
            f"This photo contains MULTIPLE parts. The tool has already LOCATED each "
            f"part and cropped it at FULL RESOLUTION: {len(crops)} PART CROPS are "
            f"attached (crop_00 .. crop_{len(crops) - 1:02d}), one part per crop, in "
            f"reading order. Inspect EACH CROP as the authoritative full-resolution "
            f"view of exactly ONE part - this is what makes a part in a collage get the "
            f"SAME scrutiny as a single-part, full-frame photo. Do this per crop:")
        lines.append("1. Identify the part in the crop against the PART REGISTRY below "
                     "(silhouette + distinguishing features, ignore orientation/lighting). "
                     "If none matches, set part to \"unknown\" -> NEEDS_REVIEW.")
        lines.append("2. Inspect it using ONLY that part's defect catalog + rulings.")
        lines.append("3. Return ONE instance PER CROP, in the SAME ORDER, each carrying "
                     "its `crop_index` (0-based).")
        lines.append("4. COORDINATES ARE CROP-LOCAL: every instance_bbox, defect bbox, "
                     "line and lines value must be normalized 0..1 RELATIVE TO ITS OWN CROP "
                     "(the crop as shown to you), NOT the whole photo. The tool maps each "
                     "crop's coordinates back onto the full image automatically.")
        lines.append("")
    else:
        lines.append(
            "No part was pre-selected. The INPUT image may contain ONE OR MORE "
            "manufactured parts. Do this in order:")
        lines.append("1. Find each distinct part instance in the image.")
        lines.append("2. Identify each against the PART REGISTRY below using its identity "
                     "signature (match on silhouette + distinguishing features, ignore "
                     "orientation/lighting). If none matches, set part to \"unknown\".")
        lines.append("3. Inspect each identified instance using ONLY that part's defect "
                     "catalog + rulings, EXAMINING EACH INSTANCE AT FULL RESOLUTION (mentally crop "
                     "to its region and zoom in before classifying, so a part that fills only a "
                     "fraction of this collage gets the same scrutiny as a full-frame photo). A part "
                     "with no known match -> NEEDS_REVIEW.")
        lines.append("4. Return ONE JSON verdict with an `instances` array (one element "
                     "per part instance). See OUTPUT FORMAT.")
        lines.append("")
    for p in bundle["parts"]:
        lines.append(f"## PART: {p['part']}")
        idn = p.get("identity", {}) or {}
        if idn.get("summary"):
            lines.append(f"IDENTITY: {idn['summary']}")
        if idn.get("distinguishing_features"):
            lines.append("Distinguishing features: " + "; ".join(idn["distinguishing_features"]))
        if idn.get("not_to_confuse_with"):
            lines.append("Do NOT confuse with: " + "; ".join(idn["not_to_confuse_with"]))
        if p.get("description"):
            lines.append(p["description"])
        lines.append("Defect catalog (only these may be reported for this part):")
        for d in p["defects"]:
            lines.append(f"  - **{d['category']}** [{d['scope']}, sev {d['severity']}]: {d['signature']}")
            lines.extend(_defect_lines(d, indent="      "))
        if p.get("rulings"):
            lines.append("Rulings:")
            for r in p["rulings"]:
                lines.append(f"  - {_prose(r)}")
        if p.get("notes"):
            lines.append("Notes:")
            for n in p["notes"]:
                lines.append(f"  - {_prose(n)}")
        lines.append("")

    lines.append("## IMAGES ATTACHED")
    for p in bundle["parts"]:
        for g in p["golden_images"]:
            lines.append(f"- GOLDEN reference ({p['part']}): {_rel(g)}")
    if multi:
        for i, cr in enumerate(crops):
            lines.append(f"- PART CROP {i} (full resolution, crop_index {i}): {cr['file']}")
        lines.append("  (Inspect each crop as one full part; coordinates are crop-local.)")
    else:
        lines.append(f"- INPUT to inspect: {_rel(bundle['image'])}")
    lines.append("")

    lines.append("## OUTPUT FORMAT (JSON only)")
    crop_note = ("crop-local normalized 0..1" if bundle.get("crops") and len(bundle["crops"]) >= 2
                 else "whole-image normalized")
    lines.append('{')
    lines.append('  "image": "<filename>",')
    lines.append('  "mode": "auto",')
    lines.append('  "instances": [')
    lines.append('    {')
    lines.append('      "part": "<identified part or \'unknown\'>",')
    lines.append(f'      "crop_index": <0-based crop number, or omit in single-image mode>,')
    lines.append(f'      "instance_bbox": [x, y, w, h],        // this part\'s region, {crop_note}')
    lines.append('      "identity_confidence": 0.0-1.0,')
    lines.append('      "result": "OK | DEFECT | NEEDS_REVIEW",')
    lines.append('      "primary": "<category or null>",')
    lines.append('      "needs_review_reason": "<string or null>",')
    lines.append(f'      "defects": [ {{ "category","scope","severity","bbox":[x,y,w,h] ({crop_note}),')
    lines.append('                     "line":[x1,y1,x2,y2] and/or "lines":[[x1,y1,x2,y2],...] for LINE-shaped')
    lines.append('                     defects (trace every scratch end-to-end; see each defect\'s ANNOTATION),')
    lines.append('                     "location","confidence","reason" } ]')
    lines.append('    }')
    lines.append('  ]')
    lines.append('}')
    lines.append("")
    if bundle["warnings"]:
        lines.append("## GROUNDING WARNINGS")
        for warn in bundle["warnings"]:
            lines.append(f"- {warn}")
        lines.append("")
    if bundle.get("crops") and len(bundle["crops"]) >= 2:
        lines.append("Now inspect EACH attached PART CROP at full resolution and return the "
                     "JSON verdict only (one instance per crop, crop-local coordinates).")
    else:
        lines.append("Now identify and inspect every part in the INPUT image and return the JSON verdict only.")
    return "\n".join(lines)



