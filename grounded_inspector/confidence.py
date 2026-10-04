"""Deterministic, explainable confidence scoring.

The reported confidence is NOT a hand-typed guess and NOT a pixel measurement. It
is COMPUTED from a small set of EVIDENCE FACTORS that are judged 0..1 BY EYE (per
INVARIANT 0c - the eye/vision model finds the evidence, code never detects the
defect), combined by the fixed formula declared in the grounding bundle
(`<defect>.confidence_model`). Because the weights live in the bundle, the dev
score and the rule the Anthropic API is given can never drift apart.

    from grounded_inspector import confidence
    score, breakdown = confidence.score("serration_missing", {
        "rim_smoothness": 1.0, "evidence_readability": 0.95, "anchor_certainty": 0.9})

`breakdown` explains every contribution (weight x factor) so any number is auditable.
"""
from __future__ import annotations

from typing import Optional

from . import loader as C


def _find_model(category: str) -> Optional[dict]:
    """Return the confidence_model dict declared for `category` in the bundle
    (global catalog first, then any part_defects), or None if none is declared."""
    key = str(category).strip().lower()
    cat = C.load_global_catalog()
    spec = (cat.get("defects", {}) or {}).get(key)
    if spec and spec.get("confidence_model"):
        return spec["confidence_model"]
    for part in C.list_parts():
        spec = (part.get("defects", {}) or {}).get(key)
        if spec and spec.get("confidence_model"):
            return spec["confidence_model"]
    return None


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def score(category: str, factors: dict) -> tuple[float, dict]:
    """Compute confidence for `category` from by-eye evidence `factors` (name -> 0..1).

    Returns (confidence 0..1, breakdown). The formula is the weighted average declared
    in the bundle's confidence_model: sum(w_i * f_i) / sum(w_i). A factor the caller
    omits is treated as 0 (missing evidence lowers confidence). Raises if the category
    has no confidence_model in the bundle (so an unscored defect is never silently
    given a fabricated number)."""
    model = _find_model(category)
    if not model:
        raise ValueError(f"no confidence_model declared in the bundle for '{category}'")
    spec_factors = model.get("factors", {}) or {}
    contributions = {}
    weighted_sum = 0.0
    weight_total = 0.0
    for name, fspec in spec_factors.items():
        w = float(fspec.get("weight", 0.0))
        v = _clamp01(float(factors.get(name, 0.0)))
        weighted_sum += w * v
        weight_total += w
        contributions[name] = {"weight": w, "value": v, "contribution": round(w * v, 4)}
    conf = _clamp01(weighted_sum / weight_total) if weight_total else 0.0
    unknown = [k for k in factors if k not in spec_factors]
    breakdown = {
        "category": str(category).lower(),
        "confidence": round(conf, 4),
        "percent": int(round(conf * 100)),
        "factors": contributions,
        "ignored_inputs": unknown,  # names not defined in the model (typo guard)
    }
    return conf, breakdown


def explain(category: str, factors: dict) -> str:
    """One-line human-readable derivation, e.g.
    'serration_missing 96% = 0.5*1.00(rim_smoothness) + 0.3*0.95(evidence_readability) + ...'."""
    conf, bd = score(category, factors)
    terms = " + ".join(
        f"{c['weight']:g}*{c['value']:.2f}({name})" for name, c in bd["factors"].items()
    )
    return f"{bd['category']} {bd['percent']}% = {terms}"
