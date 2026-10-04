"""Deterministic inspection verdict aggregation."""
from __future__ import annotations
_REVIEW="NEEDS_REVIEW"
def aggregate(bundle,anatomy,results):
    meta={d["category"]:d for d in bundle.get("defects",[])}
    checkpoints=[{"check":"anatomy","result":"CLEARED" if anatomy["status"]=="CLEAR" else _REVIEW,"evidence":"Shared anatomy established once." if anatomy["status"]=="CLEAR" else str(anatomy.get("evidence",""))}]
    defects=[]
    for r in results:
        status=r.get("status",_REVIEW)
        checkpoints.append({"check":r["defect"],"result":"DEFECT" if status=="DEFECT" else "CLEARED" if status=="CLEAR" else _REVIEW,"evidence":r.get("evidence","")})
        if status!="DEFECT": continue
        spec=meta.get(r["defect"],{})
        for loc in r.get("locations",[]):
            d={"category":r["defect"],"scope":spec.get("scope","part"),"severity":spec.get("severity",2),"bbox":list(loc["bbox"]),"confidence":round(float(loc.get("confidence",0)),2),"reason":loc.get("reason",""),"display_name":spec.get("display_name",r["defect"])}
            if loc.get("location"): d["location"]=loc["location"]
            defects.append(d)
    unresolved=anatomy["status"]!="CLEAR" or any(r.get("status")==_REVIEW for r in results)
    if unresolved: result,primary,reason=_REVIEW,None,"One or more required inspection checkpoints could not be resolved with available visual evidence."
    elif defects: result,primary,reason="DEFECT",max(defects,key=lambda d:(d["severity"],d["confidence"]))["category"],None
    else: result,primary,reason="OK",None,None
    return {"part":bundle["part"],"image":bundle["image"],"result":result,"primary":primary,"needs_review_reason":reason,"checkpoints":checkpoints,"defects":defects}
