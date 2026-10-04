"""Shared anatomy inspection stage."""
from __future__ import annotations
import json, os
from .. import grid
from .. import loader as C
from .transport import call_model
_REVIEW="NEEDS_REVIEW"
def inspect(bundle,model):
    policy=open(os.path.join(C.GROUNDING_DIR,"policy.md"),encoding="utf-8").read()
    prompt="\n".join([policy,"","# SHARED ANATOMY INSPECTION","Establish shared physical facts only. Do not classify any defect.","Use visible evidence and the authored anatomy as authoritative.","Follow anatomy decision order exactly. If a required anatomy fact is unresolved, return NEEDS_REVIEW.","Do not use dependent defect features to establish prerequisites when the anatomy says otherwise.",f"PART: {bundle['part']}",f"DESCRIPTION: {bundle.get('part_description','')}","AUTHORITATIVE ANATOMY:",json.dumps(bundle.get("anatomy") or {},ensure_ascii=False,indent=2),"",'Return JSON only: {"status":"CLEAR | NEEDS_REVIEW","facts":{},"evidence":{}}'])
    images=[("GOLDEN reference",p) for p in bundle.get("golden_images",[]) if os.path.isfile(p)]
    gp=grid.grid_for(bundle["image"])
    if gp: images.append(("INPUT with coordinate grid - localization aid only",gp))
    images.append(("INPUT to inspect",bundle["image"]))
    raw=call_model(prompt,images,model)
    status=raw.get("status") if raw.get("status") in {"CLEAR",_REVIEW} else _REVIEW
    facts=raw.get("facts") if isinstance(raw.get("facts"),dict) else {}
    evidence=raw.get("evidence") if isinstance(raw.get("evidence"),dict) else {"summary":str(raw.get("evidence") or "")}
    if "facts" not in raw: status=_REVIEW
    return {"status":status,"facts":facts,"evidence":evidence}
