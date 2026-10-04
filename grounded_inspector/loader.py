"""Configuration loading and resolution for the grounding schema."""
from __future__ import annotations
import glob, json, os
from typing import Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GROUNDING_DIR = os.path.join(ROOT, "grounding")
PARTS_DIR = os.path.join(GROUNDING_DIR, "parts")
_IMG_EXTS = ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG")


def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_global_catalog() -> dict:
    return _read_json(os.path.join(GROUNDING_DIR, "defects.json"))


def list_parts() -> List[dict]:
    return [_read_json(p) for p in sorted(glob.glob(os.path.join(PARTS_DIR, "*.json")))]


def _norm(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "_")


def load_part(name: str) -> dict:
    target = _norm(name)
    path = os.path.join(PARTS_DIR, f"{target}.json")
    if os.path.isfile(path):
        cfg = _read_json(path)
        if _norm(cfg.get("part", "")) == target:
            cfg["_path"] = path
            return cfg
    raise KeyError(f"Unknown part: {name!r}. Known: {[p['part'] for p in list_parts()]}")


def _abs(rel: str) -> str:
    return rel if os.path.isabs(rel) else os.path.join(ROOT, rel)


def _images_in(spec: str) -> List[str]:
    if not spec:
        return []
    p = _abs(spec)
    out: List[str] = []
    if os.path.isdir(p):
        for ext in _IMG_EXTS:
            out += glob.glob(os.path.join(p, ext))
    elif any(ch in spec for ch in "*?[]"):
        out += glob.glob(p)
    elif os.path.isfile(p):
        out.append(p)
    return sorted(set(out))


def pair_exemplars(paths: List[str]) -> List[dict]:
    bases: Dict[str, dict] = {}
    order: List[str] = []

    def entry(key):
        if key not in bases:
            bases[key] = {"full": None, "crop": None, "caption": None}
            order.append(key)
        return bases[key]

    for p in paths:
        stem = os.path.splitext(os.path.basename(p))[0]
        if stem.endswith("_crop"):
            entry(stem[:-5])["crop"] = p
        else:
            entry(stem)["full"] = p

    for key, e in bases.items():
        ref = e["full"] or e["crop"]
        if ref:
            side = os.path.join(os.path.dirname(ref), key + ".txt")
            if os.path.isfile(side):
                with open(side, "r", encoding="utf-8") as fh:
                    first = fh.readline().strip()
                if first:
                    e["caption"] = first
    return [bases[k] for k in order]


def _normalize_decision(spec: dict) -> dict:
    return dict(spec.get("decision") or {})


def resolve_defects(part: dict, catalog: Optional[dict] = None) -> List[dict]:
    catalog = catalog or load_global_catalog()
    resolved = []
    seen = set()

    def add(cat, spec, scope, ref_dir=None):
        key = _norm(cat)
        if key in seen:
            raise ValueError(
                f"Duplicate resolved defect category: {cat!r} for part {part.get('part')!r}"
            )
        seen.add(key)
        decision = _normalize_decision(spec)
        resolved.append({
            "category": cat,
            "scope": scope,
            "severity": spec.get("severity", 2 if scope == "global" else 3),
            "color": spec.get("color"),
            "annotation": spec.get("annotation"),
            "decision": decision,
            "reference_images": _images_in(
                ref_dir or spec.get("reference_dir", "")
            ),
        })

    for cat, spec in (catalog.get("defects", {}) or {}).items():
        if spec.get("scope") == "all":
            add(
                cat,
                spec,
                "global",
                os.path.join("grounding", "references", "global", cat),
            )

    for cat, spec in (part.get("defects", {}) or {}).items():
        add(cat, spec, "part", spec.get("reference_dir"))

    resolved.sort(key=lambda d: (-d["severity"], d["scope"] != "part"))
    return resolved


def golden_images(part: dict) -> List[str]:
    out = []
    for spec in part.get("golden_images", []) or []:
        out += _images_in(spec)
    return out
