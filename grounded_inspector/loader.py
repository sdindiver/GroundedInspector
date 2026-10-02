"""Configuration loading and resolution.

Merges the global defect catalog with a part config to produce the exact set of
defects that should be checked for a given part.
"""
from __future__ import annotations

import glob
import json
import os
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


def load_rules_library() -> dict:
    """Shared rule library (grounding/rules.json): id -> rule text (string or sentence-list).
    A rule authored ONCE here can be referenced anywhere via {"$ref": "id"} so it is
    single-sourced. Missing file = no shared rules (feature is opt-in)."""
    path = os.path.join(GROUNDING_DIR, "rules.json")
    if not os.path.isfile(path):
        return {}
    return _read_json(path).get("rules", {})


def resolve_ref(value, lib=None):
    """Expand a {"$ref": "id"} pointer to the library rule text; pass any other value through.
    Renders identically to the inline text, so referencing is behavior-preserving."""
    if isinstance(value, dict) and "$ref" in value:
        lib = load_rules_library() if lib is None else lib
        return lib.get(value["$ref"], "")
    return value


def resolve_ref_list(items) -> List:
    """Resolve every {"$ref": ...} element in a rulings/notes list (plain items pass through)."""
    lib = load_rules_library()
    return [resolve_ref(it, lib) for it in (items or [])]


def load_verification_config() -> dict:
    """Tunable thresholds for the deterministic verifier gate (verify.py).

    Config-only: the gate LOGIC ships in code, this just tunes it. Missing file =
    the gate falls back to its built-in defaults, so verification never hard-fails
    for lack of config.
    """
    path = os.path.join(GROUNDING_DIR, "verification.json")
    if not os.path.isfile(path):
        return {}
    return _read_json(path)


def list_parts() -> List[dict]:
    parts = []
    for path in sorted(glob.glob(os.path.join(PARTS_DIR, "*.json"))):
        parts.append(_read_json(path))
    return parts


def _norm(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "_")


def load_part(name: str) -> dict:
    """Look up a part config by name, alias, or file stem (case/space-insensitive)."""
    target = _norm(name)
    for path in glob.glob(os.path.join(PARTS_DIR, "*.json")):
        cfg = _read_json(path)
        stem = _norm(os.path.splitext(os.path.basename(path))[0])
        names = {stem, _norm(cfg.get("part", ""))}
        names.update(_norm(a) for a in cfg.get("aliases", []))
        if target in names:
            cfg["_path"] = path
            return cfg
    raise KeyError(f"Unknown part: {name!r}. Known: {[p['part'] for p in list_parts()]}")


def _abs(rel: str) -> str:
    return rel if os.path.isabs(rel) else os.path.join(ROOT, rel)


def _images_in(spec: str) -> List[str]:
    """Resolve a dir OR glob OR file into a sorted list of existing image paths."""
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
    """Group exemplar images into {full, crop, caption} entries so the prompt attaches each
    defect example as the FULL part image PLUS a tight localization CROP of the SAME defect
    (context + where-it-is). A file whose stem ends '_crop' is the crop of its base-stem
    sibling; an optional sidecar '<base>.txt' gives a one-line locator caption. Orphans (a
    crop with no full, or a full with no crop) still pass through in first-seen order."""
    bases: Dict[str, dict] = {}
    order: List[str] = []

    def _entry(key: str) -> dict:
        if key not in bases:
            bases[key] = {"full": None, "crop": None, "caption": None}
            order.append(key)
        return bases[key]

    for p in paths:
        stem = os.path.splitext(os.path.basename(p))[0]
        if stem.endswith("_crop"):
            _entry(stem[:-5])["crop"] = p
        else:
            _entry(stem)["full"] = p
    for key, e in bases.items():
        ref = e["full"] or e["crop"]
        if not ref:
            continue
        side = os.path.join(os.path.dirname(ref), key + ".txt")
        if os.path.isfile(side):
            with open(side, "r", encoding="utf-8") as fh:
                first = fh.readline().strip()
            if first:
                e["caption"] = first
    return [bases[k] for k in order]


def resolve_defects(part: dict, catalog: Optional[dict] = None) -> List[dict]:
    """Return the ordered, resolved defect list for a part.

    Includes every global scope=='all' defect (minus excludes), every opt-in
    global the part requested, then the part-specific defects. Each entry is
    normalized to: category, scope, severity, color, signature, reference_images.
    """
    catalog = catalog or load_global_catalog()
    lib = load_rules_library()
    gd = part.get("global_defects", {}) or {}
    exclude = {_norm(x) for x in gd.get("exclude", [])}
    include_opt_in = {_norm(x) for x in gd.get("include_opt_in", [])}

    # structural keys handled explicitly; everything else is free-form grounding
    # guidance (disambiguation, glare_rule, ...) that must reach the prompt bundle.
    _structural = {"severity", "color", "scope", "signature", "annotation",
                   "reference_dir", "reference_images"}

    resolved: List[dict] = []

    for cat, spec in catalog.get("defects", {}).items():
        scope_flag = spec.get("scope", "all")
        keep = (scope_flag == "all" and _norm(cat) not in exclude) or (
            scope_flag == "opt_in" and _norm(cat) in include_opt_in
        )
        if not keep:
            continue
        resolved.append({
            "category": cat,
            "scope": "global",
            "severity": spec.get("severity", 2),
            "color": spec.get("color"),
            "signature": spec.get("signature", ""),
            "annotation": spec.get("annotation"),
            "guidance": {k: resolve_ref(v, lib) for k, v in spec.items() if k not in _structural},
            "reference_images": _images_in(os.path.join("grounding", "references", "global", cat)),
        })

    for cat, spec in (part.get("part_defects", {}) or {}).items():
        resolved.append({
            "category": cat,
            "scope": "part",
            "severity": spec.get("severity", 3),
            "color": spec.get("color"),
            "signature": spec.get("signature", ""),
            "annotation": spec.get("annotation"),
            "guidance": {k: resolve_ref(v, lib) for k, v in spec.items() if k not in _structural},
            "reference_images": _images_in(spec.get("reference_dir", "")),
        })

    resolved.sort(key=lambda d: (-d["severity"], d["scope"] != "part"))
    return resolved


def golden_images(part: dict) -> List[str]:
    out: List[str] = []
    for spec in part.get("golden_images", []) or []:
        out += _images_in(spec)
    return out


def part_identities(max_golden: int = 1) -> List[dict]:
    """Registry of every known part's identity signature + a golden thumbnail.

    Used to build the auto-identification bundle: the engine matches the input
    image against these signatures to decide which part(s) are present before it
    inspects. Each entry: part, aliases, identity, golden_images (capped).
    """
    out: List[dict] = []
    for cfg in list_parts():
        golden = golden_images(cfg)[:max_golden] if max_golden else golden_images(cfg)
        out.append({
            "part": cfg.get("part", ""),
            "aliases": cfg.get("aliases", []),
            "description": cfg.get("description", ""),
            "identity": cfg.get("identity", {}),
            "golden_images": golden,
        })
    return out
