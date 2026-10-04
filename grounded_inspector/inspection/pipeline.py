"""Production modular pipeline for explicit-part and auto-identification inspection."""
from __future__ import annotations
import json, os, tempfile
from PIL import Image
from .. import assembler, loader as C
from . import anatomy, defect
from .aggregator import aggregate
from .transport import call_model
_REVIEW="NEEDS_REVIEW"
def inspect_part(part,image_path,model):
    bundle=assembler.build_bundle(part,image_path)
    a=anatomy.inspect(bundle,model)
    by={d["category"]:d for d in bundle.get("defects",[])}
    ordered=[by[c] for c in bundle.get("inspection",[]) if c!="orientation" and c in by]
    return aggregate(bundle,a,[defect.inspect(bundle,d,a,model) for d in ordered])
def _identify(image_path,parts,model):
    policy=open(os.path.join(C.GROUNDING_DIR,"policy.md"),encoding="utf-8").read()
    catalog=[{"part":p["part"],"description":p.get("description",""),"anatomy":p.get("anatomy",{})} for p in parts]
    prompt="\n".join([policy,"","# PART IDENTIFICATION STAGE","Identify every distinct configured part instance in the input image.","This stage ONLY identifies part instances and image regions. Do not inspect defects.","Use canonical part names only. If an instance cannot be confidently matched, return part='unknown' and NEEDS_REVIEW.","Do not merge separate parts. Coordinates are normalized 0..1.","PART CATALOG:",json.dumps(catalog,ensure_ascii=False,indent=2),"",'Return JSON only: {"instances":[{"part":"<canonical name or unknown>","bbox":[x,y,w,h],"identity_confidence":0.0,"status":"IDENTIFIED | NEEDS_REVIEW"}]}'])
    images=[]
    for p in parts:
        for g in p.get("golden_images",[]):
            if os.path.isfile(g): images.append((f"GOLDEN reference ({p['part']})",g))
    images.append(("INPUT to identify",image_path))
    raw=call_model(prompt,images,model); known={p["part"] for p in parts}; out=[]
    for item in raw.get("instances") or []:
        bb=item.get("bbox"); part=item.get("part")
        try: conf=max(0,min(1,float(item.get("identity_confidence",0) or 0)))
        except (TypeError,ValueError): conf=0
        valid=isinstance(bb,list) and len(bb)==4 and all(isinstance(v,(int,float)) for v in bb) and part in known and item.get("status")=="IDENTIFIED"
        out.append({"part":part if part in known else "unknown","bbox":bb if isinstance(bb,list) and len(bb)==4 else [0,0,1,1],"identity_confidence":conf,"status":"IDENTIFIED" if valid else _REVIEW})
    return out or [{"part":"unknown","bbox":[0,0,1,1],"identity_confidence":0.0,"status":_REVIEW}]
def _crop(image_path,bbox,tmpdir):
    img=Image.open(image_path).convert("RGB"); W,H=img.size
    x,y,w,h=[float(v) for v in bbox]; x=max(0,min(1,x)); y=max(0,min(1,y)); w=max(0,min(1-x,w)); h=max(0,min(1-y,h))
    px=min(.08,w*.08); py=min(.08,h*.08); box=(max(0,x-px),max(0,y-py),min(1,x+w+px),min(1,y+h+py))
    path=os.path.join(tmpdir,"instance.png"); img.crop((int(box[0]*W),int(box[1]*H),int(box[2]*W),int(box[3]*H))).save(path); return path,box
def _to_full(bbox,box):
    x0,y0,wc,hc=box; x,y,w,h=[float(v) for v in bbox]; return [x0+x*wc,y0+y*hc,w*wc,h*hc]
def inspect_auto(image_path,model):
    parts=[{"part":cfg["part"],"description":cfg.get("description",""),"anatomy":cfg.get("anatomy",{}),"golden_images":C.golden_images(cfg)[:1]} for cfg in C.list_parts()]
    instances=_identify(image_path,parts,model); output=[]
    with tempfile.TemporaryDirectory(prefix="grounded-inspector-") as tmpdir:
        for i,inst in enumerate(instances):
            base={"part":inst["part"],"crop_index":i,"instance_bbox":inst["bbox"],"identity_confidence":inst["identity_confidence"]}
            if inst["status"]!="IDENTIFIED":
                base.update({"result":_REVIEW,"primary":None,"needs_review_reason":"Part identity could not be established reliably.","defects":[],"checkpoints":[]}); output.append(base); continue
            crop,box=_crop(image_path,inst["bbox"],tmpdir)
            verdict=inspect_part(inst["part"],crop,model)
            verdict.update({"image":os.path.basename(image_path),"crop_index":i,"instance_bbox":inst["bbox"],"identity_confidence":inst["identity_confidence"]})
            for d in verdict["defects"]: d["bbox"]=_to_full(d["bbox"],box)
            output.append(verdict)
    return {"image":os.path.basename(image_path),"mode":"auto","instances":output}
