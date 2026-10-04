"""Configuration loading and resolution for the normalized grounding schema."""
from __future__ import annotations
import glob, json, os
from typing import Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GROUNDING_DIR = os.path.join(ROOT, "grounding")
PARTS_DIR = os.path.join(GROUNDING_DIR, "parts")
_IMG_EXTS = ("*.jpg","*.jpeg","*.png","*.JPG","*.JPEG","*.PNG")

def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)

def load_global_catalog() -> dict:
    return _read_json(os.path.join(GROUNDING_DIR, "defects.json"))

def load_global_rules() -> dict:
    path = os.path.join(GROUNDING_DIR, "global_rules.json")
    if not os.path.isfile(path):
        return {}
    return _read_json(path)

def load_verification_config() -> dict:
    path = os.path.join(GROUNDING_DIR, "verification.json")
    return _read_json(path) if os.path.isfile(path) else {}

def list_parts() -> List[dict]:
    return [_read_json(p) for p in sorted(glob.glob(os.path.join(PARTS_DIR, "*.json")))]

def _norm(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "_")

def load_part(name: str) -> dict:
    target = _norm(name)
    for path in glob.glob(os.path.join(PARTS_DIR, "*.json")):
        cfg = _read_json(path)
        names = {_norm(os.path.splitext(os.path.basename(path))[0]), _norm(cfg.get("part",""))}
        names.update(_norm(a) for a in cfg.get("aliases", []))
        if target in names:
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
        for ext in _IMG_EXTS: out += glob.glob(os.path.join(p, ext))
    elif any(ch in spec for ch in "*?[]"):
        out += glob.glob(p)
    elif os.path.isfile(p):
        out.append(p)
    return sorted(set(out))

def pair_exemplars(paths: List[str]) -> List[dict]:
    bases: Dict[str,dict] = {}; order: List[str] = []
    def entry(key):
        if key not in bases:
            bases[key]={"full":None,"crop":None,"caption":None}; order.append(key)
        return bases[key]
    for p in paths:
        stem=os.path.splitext(os.path.basename(p))[0]
        if stem.endswith("_crop"): entry(stem[:-5])["crop"]=p
        else: entry(stem)["full"]=p
    for key,e in bases.items():
        ref=e["full"] or e["crop"]
        if ref:
            side=os.path.join(os.path.dirname(ref),key+".txt")
            if os.path.isfile(side):
                with open(side,"r",encoding="utf-8") as fh:
                    first=fh.readline().strip()
                if first: e["caption"]=first
    return [bases[k] for k in order]

def _normalize_decision(spec: dict) -> dict:
    decision = dict(spec.get("decision") or {})
    if not decision:
        # Legacy configs remain readable during migration.
        decision = {"check": spec.get("signature",""), **{
            k: spec[k] for k in ("disambiguation","false_positive_rule","classification_rule",
                                 "pattern_match_protocol","glare_rule","localization")
            if k in spec
        }}
    return decision

def resolve_defects(part: dict, catalog: Optional[dict] = None) -> List[dict]:
    catalog = catalog or load_global_catalog()
    gd = part.get("global_defects", {}) or {}
    exclude = {_norm(x) for x in gd.get("exclude", [])}
    include_opt_in = {_norm(x) for x in gd.get("include_opt_in", [])}
    include = {_norm(x) for x in (part.get("include_defects", []) or [])}
    resolved=[]; seen=set()

    def add(cat, spec, scope, ref_dir=None):
        key=_norm(cat)
        if key in seen:
            raise ValueError(f"Duplicate resolved defect category: {cat!r} for part {part.get('part')!r}")
        seen.add(key)
        decision=_normalize_decision(spec)
        resolved.append({
            "category": cat, "scope": scope,
            "severity": spec.get("severity", 2 if scope=="global" else 3),
            "color": spec.get("color"),
            "signature": spec.get("signature") or decision.get("check",""),
            "annotation": spec.get("annotation"),
            "decision": decision,
            "guidance": {},
            "reference_images": _images_in(ref_dir or spec.get("reference_dir","")),
        })

    for cat,spec in (catalog.get("defects",{}) or {}).items():
        scope=spec.get("scope","all")
        keep=(scope=="all" and _norm(cat) not in exclude) or (scope=="opt_in" and _norm(cat) in include_opt_in)
        if keep: add(cat,spec,"global",os.path.join("grounding","references","global",cat))
    part_defs=part.get("defects", part.get("part_defects", {})) or {}
    for cat,spec in part_defs.items(): add(cat,spec,"part",spec.get("reference_dir"))
    for cat in include:
        if cat not in seen and cat in { _norm(x) for x in (catalog.get("defects",{}) or {}) }:
            real=next(k for k in catalog["defects"] if _norm(k)==cat); add(real,catalog["defects"][real],"global",
                os.path.join("grounding","references","global",real))
    resolved.sort(key=lambda d:(-d["severity"], d["scope"]!="part"))
    return resolved

def golden_images(part: dict) -> List[str]:
    out=[]
    for spec in part.get("golden_images",[]) or []: out += _images_in(spec)
    return out

def part_identities(max_golden: int=1) -> List[dict]:
    out=[]
    for cfg in list_parts():
        out.append({
            "part":cfg.get("part",""),"aliases":cfg.get("aliases",[]),
            "description":cfg.get("description",""),"identity":cfg.get("identity",{}),
            "golden_images":golden_images(cfg)[:max_golden] if max_golden else golden_images(cfg)
        })
    return out
