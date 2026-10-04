"""Modular inspection pipeline: shared anatomy, independent defect inspectors, deterministic aggregation."""
from __future__ import annotations
import base64, io, json, os
from typing import List, Tuple
from . import assembler, grid
from . import loader as C

_MEDIA = {".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg"}
_REVIEW = "NEEDS_REVIEW"

def _encode_image(path: str) -> dict:
    ext = os.path.splitext(path)[1].lower()
    with open(path, "rb") as fh:
        data = fh.read()
    from PIL import Image
    with Image.open(io.BytesIO(data)) as im:
        if max(im.size) > 2000:
            im.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            im.save(out, format="PNG" if ext == ".png" else "JPEG", quality=95)
            data = out.getvalue()
    return {"type":"image","source":{"type":"base64","media_type":_MEDIA.get(ext,"image/png"),
            "data":base64.standard_b64encode(data).decode("ascii")}}

def _call(prompt: str, images: List[Tuple[str,str]], model: str) -> dict:
    try:
        import truststore
        truststore.inject_into_ssl()
        import anthropic
    except ImportError as exc:
        raise RuntimeError("API dependencies are not installed. Run: pip install -r requirements.txt") from exc
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set.")
    content=[{"type":"text","text":prompt}]
    for label,path in images:
        content.append({"type":"text","text":f"[{label}]"})
        content.append(_encode_image(path))
    msg=anthropic.Anthropic().messages.create(
        model=model,max_tokens=3000,messages=[{"role":"user","content":content}]
    )
    text="".join(b.text for b in msg.content if getattr(b,"type","")=="text").strip()
    start,end=text.find("{"),text.rfind("}")
    if start<0 or end<0:
        raise ValueError(f"No JSON object found in engine reply:\n{text[:400]}")
    return json.loads(text[start:end+1])

def _grid_image(bundle):
    p=grid.grid_for(bundle["image"])
    return p if p and os.path.isfile(p) else None

def _anatomy_prompt(bundle):
    return "\n".join([
        "# SHARED ANATOMY INSPECTION",
        "Establish shared physical facts only. Do not classify any defect.",
        "Use visible evidence and the authored anatomy as authoritative.",
        "Follow anatomy decision order exactly. If a required anatomy fact is unresolved, return NEEDS_REVIEW.",
        "Do not use dependent defect features to establish prerequisites when the anatomy says otherwise.",
        "",
        f"PART: {bundle['part']}",
        f"DESCRIPTION: {bundle.get('part_description','')}",
        "AUTHORITATIVE ANATOMY:",
        json.dumps(bundle.get("anatomy") or {},ensure_ascii=False,indent=2),
        "",
        'Return JSON only: {"status":"CLEAR | NEEDS_REVIEW","facts":{},"evidence":{}}'
    ])

def _inspect_anatomy(bundle, model):
    images=[("GOLDEN reference",p) for p in bundle.get("golden_images",[]) if os.path.isfile(p)]
    gp=_grid_image(bundle)
    if gp: images.append(("INPUT with coordinate grid - localization aid only",gp))
    images.append(("INPUT to inspect",bundle["image"]))
    raw=_call(_anatomy_prompt(bundle),images,model)
    status=raw.get("status")
    if status not in {"CLEAR",_REVIEW}: status=_REVIEW
    facts=raw.get("facts") if isinstance(raw.get("facts"),dict) else {}
    evidence=raw.get("evidence")
    if not isinstance(evidence,dict): evidence={"summary":str(evidence or "")}
    if not facts: status=_REVIEW if not raw.get("facts") else status
    return {"status":status,"facts":facts,"evidence":evidence}

def _defect_prompt(bundle, defect, anatomy):
    return "\n".join([
        "# INDEPENDENT DEFECT INSPECTION",
        "Evaluate ONLY the named defect. Do not classify, mention, or suppress unrelated defects.",
        "Do not reinterpret shared anatomy. Do not use another defect as evidence.",
        "Use the shared anatomy facts as prerequisites. If anatomy is unresolved, return NEEDS_REVIEW.",
        "Use only visible evidence. Use attached exemplars for this defect only.",
        "",
        f"PART: {bundle['part']}",
        f"DEFECT: {defect['category']}",
        f"DISPLAY NAME: {defect.get('display_name',defect['category'])}",
        f"SEVERITY: {defect.get('severity',0)}",
        "SHARED ANATOMY STATUS:",
        anatomy["status"],
        "SHARED ANATOMY FACTS:",
        json.dumps(anatomy["facts"],ensure_ascii=False,indent=2),
        "AUTHORITATIVE DEFECT DECISION:",
        json.dumps(defect.get("decision") or {},ensure_ascii=False,indent=2),
        "",
        'Return JSON only: {"defect":"<name>","status":"DEFECT | CLEAR | NEEDS_REVIEW","evidence":"...","locations":[{"bbox":[x,y,w,h],"location":"...","confidence":0.0,"reason":"..."}]}',
        "For CLEAR or NEEDS_REVIEW, locations must be []. Coordinates are normalized 0..1."
    ])

def _inspect_defect(bundle, defect, anatomy, model):
    if anatomy["status"]==_REVIEW:
        return {"defect":defect["category"],"status":_REVIEW,
                "evidence":"A required shared anatomy prerequisite is unresolved.","locations":[]}
    images=[]
    for pair in C.pair_exemplars(defect.get("reference_images",[])):
        if pair.get("full") and os.path.isfile(pair["full"]):
            label=f"DEFECT exemplar ({defect['category']}) FULL part"
            if pair.get("caption"): label += f" - {pair['caption']}"
            images.append((label,pair["full"]))
        if pair.get("crop") and os.path.isfile(pair["crop"]):
            images.append((f"DEFECT exemplar ({defect['category']}) LOCALIZED CROP - defect HERE",pair["crop"]))
    gp=_grid_image(bundle)
    if gp: images.append(("INPUT with coordinate grid - localization aid",gp))
    images.append(("INPUT to inspect",bundle["image"]))
    raw=_call(_defect_prompt(bundle,defect,anatomy),images,model)
    status=raw.get("status")
    if status not in {"DEFECT","CLEAR",_REVIEW}: status=_REVIEW
    locations=[]
    if status=="DEFECT":
        for loc in raw.get("locations") or []:
            bbox=loc.get("bbox")
            if isinstance(bbox,list) and len(bbox)==4:
                try: conf=float(loc.get("confidence",0) or 0)
                except (TypeError,ValueError): conf=0
                if conf>1: conf/=100
                locations.append({"bbox":list(bbox),"location":loc.get("location",""),
                                  "confidence":max(0,min(1,conf)),"reason":loc.get("reason","")})
        if not locations: status=_REVIEW
    return {"defect":defect["category"],"status":status,
            "evidence":str(raw.get("evidence","")),"locations":locations}

def _aggregate(bundle, anatomy, results):
    meta={d["category"]:d for d in bundle.get("defects",[])}
    checkpoints=[{"check":"anatomy",
                  "result":"CLEARED" if anatomy["status"]=="CLEAR" else _REVIEW,
                  "evidence":"Shared anatomy established once." if anatomy["status"]=="CLEAR"
                             else str(anatomy.get("evidence",""))}]
    defects=[]
    for r in results:
        status=r.get("status",_REVIEW)
        checkpoints.append({"check":r["defect"],
                            "result":"DEFECT" if status=="DEFECT" else "CLEARED" if status=="CLEAR" else _REVIEW,
                            "evidence":r.get("evidence","")})
        if status!="DEFECT": continue
        spec=meta.get(r["defect"],{})
        for loc in r.get("locations",[]):
            d={"category":r["defect"],"scope":spec.get("scope","part"),
               "severity":spec.get("severity",2),"bbox":list(loc["bbox"]),
               "confidence":round(float(loc.get("confidence",0)),2),
               "reason":loc.get("reason",""),
               "display_name":spec.get("display_name",r["defect"])}
            if loc.get("location"): d["location"]=loc["location"]
            defects.append(d)
    if defects:
        result="DEFECT"
        primary=max(defects,key=lambda d:(d["severity"],d["confidence"]))["category"]
        review_reason=None
    elif anatomy["status"]!= "CLEAR" or any(r.get("status")==_REVIEW for r in results):
        result=_REVIEW
        primary=None
        review_reason="One or more required inspection checkpoints could not be resolved with available visual evidence."
    else:
        result="OK"; primary=None; review_reason=None
    return {"part":bundle["part"],"image":bundle["image"],"result":result,
            "primary":primary,"needs_review_reason":review_reason,
            "checkpoints":checkpoints,"defects":defects}

def inspect_image(part: str, image_path: str, model: str) -> dict:
    """Run shared anatomy once, then each configured defect independently."""
    if not part: raise ValueError("The modular pipeline requires an explicit part.")
    bundle=assembler.build_bundle(part,image_path)
    anatomy=_inspect_anatomy(bundle,model)
    by_category={d["category"]:d for d in bundle.get("defects",[])}
    ordered=[by_category[c] for c in bundle.get("inspection",[])
             if c!="orientation" and c in by_category]
    results=[_inspect_defect(bundle,d,anatomy,model) for d in ordered]
    return _aggregate(bundle,anatomy,results)
