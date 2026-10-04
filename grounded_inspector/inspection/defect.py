"""Independent defect inspection stage."""
from __future__ import annotations
import json, os
from .. import grid
from .. import loader as C
from .transport import call_model
_REVIEW="NEEDS_REVIEW"
def inspect(bundle,defect,anatomy,model):
    policy=open(os.path.join(C.GROUNDING_DIR,"policy.md"),encoding="utf-8").read()
    prompt="\n".join([policy,"","# INDEPENDENT DEFECT INSPECTION","Evaluate ONLY the named defect. Do not classify, mention, or suppress unrelated defects.","Do not reinterpret shared anatomy. Do not use another defect as evidence.","Use the shared anatomy facts as prerequisites. If anatomy is unresolved, return NEEDS_REVIEW.","Use only visible evidence. Use attached exemplars for this defect only.",f"PART: {bundle['part']}",f"DEFECT: {defect['category']}",f"DISPLAY NAME: {defect.get('display_name',defect['category'])}",f"SEVERITY: {defect.get('severity',0)}","SHARED ANATOMY STATUS:",anatomy["status"],"SHARED ANATOMY FACTS:",json.dumps(anatomy["facts"],ensure_ascii=False,indent=2),"AUTHORITATIVE DEFECT DECISION:",json.dumps(defect.get("decision") or {},ensure_ascii=False,indent=2),"",'Return JSON only: {"defect":"<name>","status":"DEFECT | CLEAR | NEEDS_REVIEW","evidence":"...","locations":[{"bbox":[x,y,w,h],"location":"...","confidence":0.0,"reason":"..."}]}',"For CLEAR or NEEDS_REVIEW, locations must be []. Coordinates are normalized 0..1."])
    if anatomy["status"]==_REVIEW: return {"defect":defect["category"],"status":_REVIEW,"evidence":"A required shared anatomy prerequisite is unresolved.","locations":[]}
    images=[]
    for pair in C.pair_exemplars(defect.get("reference_images",[])):
        if pair.get("full") and os.path.isfile(pair["full"]): images.append((f"DEFECT exemplar ({defect['category']}) FULL part",pair["full"]))
        if pair.get("crop") and os.path.isfile(pair["crop"]): images.append((f"DEFECT exemplar ({defect['category']}) LOCALIZED CROP - defect HERE",pair["crop"]))
    gp=grid.grid_for(bundle["image"])
    if gp: images.append(("INPUT with coordinate grid - localization aid",gp))
    images.append(("INPUT to inspect",bundle["image"]))
    raw=call_model(prompt,images,model)
    status=raw.get("status") if raw.get("status") in {"DEFECT","CLEAR",_REVIEW} else _REVIEW
    locations=[]
    if status=="DEFECT":
        for loc in raw.get("locations") or []:
            bbox=loc.get("bbox")
            if isinstance(bbox,list) and len(bbox)==4:
                try: conf=float(loc.get("confidence",0) or 0)
                except (TypeError,ValueError): conf=0
                if conf>1: conf/=100
                locations.append({"bbox":list(bbox),"location":loc.get("location",""),"confidence":max(0,min(1,conf)),"reason":loc.get("reason","")})
        if not locations: status=_REVIEW
    return {"defect":defect["category"],"status":status,"evidence":str(raw.get("evidence","")),"locations":locations}
