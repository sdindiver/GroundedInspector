"""Assemble grounding configuration into the existing inspection prompt/output contract."""
from __future__ import annotations
import json, os
from datetime import datetime
from typing import List
from . import loader as C

ROOT = C.ROOT
GROUNDING_DIR = C.GROUNDING_DIR
RUNS_DIR = os.path.join(ROOT, "runs")
AUTO = "__auto__"


def is_auto(part_name: str) -> bool:
    return (part_name or "").strip().lower() in (
        AUTO, "auto", "", "auto-detect", "auto_detect"
    )


def _system_prompt() -> str:
    parts = []
    for name in ("policy.md", "system_prompt.md"):
        with open(os.path.join(GROUNDING_DIR, name), encoding="utf-8") as fh:
            parts.append(fh.read())
    return "\n\n---\n\n".join(parts)


def _rel(path: str) -> str:
    try:
        return os.path.relpath(path, ROOT)
    except ValueError:
        return path


def _decision_lines(d: dict, indent="    ") -> List[str]:
    dec = d.get("decision") or {}
    out = []
    labels = [
        ("check", "CHECK"),
        ("defect_when", "DEFECT WHEN"),
        ("clear_when", "CLEAR WHEN"),
        ("review_when", "REVIEW WHEN"),
        ("boundary", "BOUNDARY"),
        ("enumeration", "ENUMERATION"),
        ("localization", "LOCALIZATION"),
    ]
    for key, label in labels:
        v = dec.get(key)
        if v is None:
            continue
        if isinstance(v, (list, tuple)):
            v = " ".join(map(str, v))
        if isinstance(v, dict):
            v = json.dumps(v, ensure_ascii=False, sort_keys=True)
        out.append(f"{indent}{label}: {v}")
    ign = dec.get("ignore") or []
    if ign:
        out.append(f"{indent}IGNORE: " + "; ".join(map(str, ign)))
    return out


def _render_defects(lines: List[str], defects, indent=""):
    for d in defects:
        check = (d.get("decision") or {}).get("check", "")
        lines.append(
            f"{indent}- **{d['category']}** [severity {d['severity']}]: {check}"
        )
        lines.extend(_decision_lines(d, indent + "    "))


def build_bundle(part_name: str, image_path: str) -> dict:
    part = C.load_part(part_name)
    catalog = C.load_global_catalog()
    defects = C.resolve_defects(part, catalog)
    golden = C.golden_images(part)
    return {
        "part": part.get("part", part_name),
        "part_description": part.get("description", ""),
        "anatomy": part.get("anatomy", {}) or {},
        "inspection": part.get("inspection", []) or [],
        "image": os.path.abspath(image_path),
        "golden_images": golden,
        "defects": defects,
        "warnings": _warnings(golden, defects, image_path),
    }


def _warnings(golden, defects, image_path):
    w = []
    if not golden:
        w.append("No golden reference image found - grounding is weaker.")
    if not os.path.isfile(image_path):
        w.append(f"Input image not found on disk: {image_path}")
    for d in defects:
        if d["scope"] == "part" and not d["reference_images"]:
            w.append(
                f"Part defect '{d['category']}' has no reference images - add exemplars if useful."
            )
    return w


def _append_part_context(lines: List[str], part: dict, *, compact: bool = False) -> None:
    if compact:
        if part.get("description"):
            lines.append("DESCRIPTION: " + part["description"])
        if part.get("anatomy"):
            lines.append("ANATOMY: " + json.dumps(part["anatomy"], ensure_ascii=False))
        if part.get("inspection"):
            lines.append("INSPECTION: " + " → ".join(part["inspection"]))
        lines.append("DEFECT DECISIONS:")
    else:
        if part.get("description"):
            lines.append(part["description"])
        if part.get("anatomy"):
            lines.extend(["## ANATOMY", json.dumps(part["anatomy"], ensure_ascii=False, indent=2)])
        if part.get("inspection"):
            lines.extend(["## INSPECTION PLAN", " → ".join(part["inspection"])])
        lines.extend(["", "## DEFECT DECISIONS (only these categories may be reported)"])
    _render_defects(lines, part["defects"])


def _append_exemplar_images(lines: List[str], defects) -> None:
    for d in defects:
        for pair in C.pair_exemplars(d["reference_images"]):
            cap = f" - {pair['caption']}" if pair.get("caption") else ""
            if pair["full"]:
                lines.append(
                    f"- DEFECT exemplar ({d['category']}) FULL part: "
                    f"{_rel(pair['full'])}{cap}"
                )
            if pair["crop"]:
                lines.append(
                    f"  -> LOCALIZED CROP of {d['category']}: {_rel(pair['crop'])}"
                )


def render_prompt(bundle: dict) -> str:
    lines = [_system_prompt(), "\n---\n", f"# PART: {bundle['part']}"]
    _append_part_context(lines, bundle)
    lines.append("")
    lines.append("## IMAGES ATTACHED")
    for g in bundle["golden_images"]:
        lines.append(f"- GOLDEN reference: {_rel(g)}")
    _append_exemplar_images(lines, bundle["defects"])
    lines.append(f"- INPUT to inspect: {_rel(bundle['image'])}")
    if bundle["warnings"]:
        lines.extend(["", "## GROUNDING WARNINGS"])
        lines.extend("- " + w for w in bundle["warnings"])
    lines.extend(["", "Now inspect the INPUT image and return the JSON verdict only."])
    return "\n".join(lines)


def write_bundle(part_name, image_path, run_dir=None) -> str:
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
            {k: d[k] for k in ("category", "scope", "severity")}
            for d in bundle["defects"]
        ],
        "warnings": bundle["warnings"],
    }
    with open(os.path.join(run_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    with open(os.path.join(run_dir, "prompt.md"), "w", encoding="utf-8") as fh:
        fh.write(render_prompt(bundle))
    return run_dir


def build_auto_bundle(image_path: str) -> dict:
    catalog = C.load_global_catalog()
    parts = []
    for cfg in C.list_parts():
        parts.append({
            "part": cfg["part"],
            "description": cfg.get("description", ""),
            "anatomy": cfg.get("anatomy", {}) or {},
            "inspection": cfg.get("inspection", []) or [],
            "golden_images": C.golden_images(cfg)[:1],
            "defects": C.resolve_defects(cfg, catalog),
        })
    warnings = []
    if not os.path.isfile(image_path):
        warnings.append(f"Input image not found on disk: {image_path}")
    if not parts:
        warnings.append("No parts are configured - add at least one grounding/parts/*.json.")
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
    lines = [_system_prompt(), "\n---\n", "# MODE: AUTO-IDENTIFY THEN INSPECT"]
    lines.append(
        "Identify each part from its canonical name, description, anatomy, and "
        "golden reference. Then inspect it using only that part's anatomy, "
        "inspection plan and defect decisions."
    )
    lines.append(
        (f"Inspect EACH of the {len(crops)} attached part crops independently; "
         "return one instance per crop in crop order. Coordinates are crop-local.")
        if multi else
        "Find each distinct part instance, identify it, inspect it at full "
        "resolution, and return one instance per part."
    )
    for p in bundle["parts"]:
        lines.append(f"\n## PART: {p['part']}")
        _append_part_context(lines, p, compact=True)
    lines.append("\n## IMAGES ATTACHED")
    for p in bundle["parts"]:
        for g in p["golden_images"]:
            lines.append(f"- GOLDEN reference ({p['part']}): {_rel(g)}")
    if multi:
        for i, cr in enumerate(crops):
            lines.append(
                f"- PART CROP {i} (full resolution, crop_index {i}): {cr['file']}"
            )
    else:
        lines.append(f"- INPUT to inspect: {_rel(bundle['image'])}")
    lines += [
        "",
        "## OUTPUT FORMAT (JSON only)",
        "{",
        '  "image": "<filename>",',
        '  "mode": "auto",',
        '  "instances": [',
        "    {",
        "      \"part\": \"<identified part or 'unknown'>\",",
        '      "crop_index": <0-based crop number, or omit in single-image mode>,',
        '      "instance_bbox": [x, y, w, h],',
        '      "identity_confidence": 0.0-1.0,',
        '      "result": "OK | DEFECT | NEEDS_REVIEW",',
        '      "primary": "<category or null>",',
        '      "needs_review_reason": "<string or null>",',
        '      "defects": [ { "category","scope","severity","bbox":[x,y,w,h], "location","confidence","reason" } ]',
        "    }",
        "  ]",
        "}",
        "",
    ]
    if bundle["warnings"]:
        lines += ["## GROUNDING WARNINGS"] + ["- " + w for w in bundle["warnings"]] + [""]
    lines.append("Now inspect and return the JSON verdict only.")
    return "\n".join(lines)

