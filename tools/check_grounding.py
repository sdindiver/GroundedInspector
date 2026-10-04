"""Validate the normalized grounding schema.

This validator checks structure and decision completeness, not prose wording.
That makes grounding safe to simplify without creating a second prose-based
source of truth.
"""
from __future__ import annotations
import json, os, sys
HERE=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0,HERE)
from grounded_inspector import loader as C

REQUIRED_DECISION={"check","defect_when","clear_when","review_when"}
FAIL=[]

def fail(msg): FAIL.append(msg)

def check_defect(cat,spec,where):
    if not isinstance(spec,dict): fail(f"{where}.{cat}: must be an object"); return
    if not spec.get("display_name"): fail(f"{where}.{cat}: missing display_name")
    if "severity" not in spec: fail(f"{where}.{cat}: missing severity")
    dec=spec.get("decision")
    if not isinstance(dec,dict):
        fail(f"{where}.{cat}: missing decision object"); return
    missing=REQUIRED_DECISION-set(dec)
    if missing: fail(f"{where}.{cat}: decision missing {sorted(missing)}")
    if not (dec.get("ignore") is not None): fail(f"{where}.{cat}: decision missing ignore list")
    if not (dec.get("localization") or spec.get("annotation")):
        # Some defects can use the engine's generic bbox, but explicit localization
        # is preferred for human-maintainable grounding.
        fail(f"{where}.{cat}: missing localization")
    if spec.get("scope") not in ("all","opt_in","part"):
        fail(f"{where}.{cat}: invalid scope {spec.get('scope')!r}")

def main():
    cat=C.load_global_catalog().get("defects",{})
    ids=set()
    for name,spec in cat.items():
        if name in ids: fail(f"duplicate global defect: {name}")
        ids.add(name); check_defect(name,spec,"global")
    for part in C.list_parts():
        p=part.get("part","?")
        defs=part.get("defects",{}) or {}
        local=set()
        for name,spec in defs.items():
            if name in local: fail(f"{p}: duplicate part defect {name}")
            local.add(name)
            if name in cat: fail(f"{p}: defect {name} duplicates a global category; keep one owner")
            check_defect(name,spec,f"part:{p}")
        plan=part.get("inspection",[])
        if not plan: fail(f"{p}: missing inspection plan")
        unknown=[x for x in plan if x not in ids and x not in local and x!="orientation"]
        if unknown: fail(f"{p}: inspection references undefined defects: {unknown}")
        if len(plan)!=len(set(plan)): fail(f"{p}: inspection plan contains duplicates")
    if FAIL:
        print("GROUNDING VALIDATION FAILED")
        for x in FAIL: print("  x",x)
        return 1
    print(f"GROUNDING VALIDATION PASSED: {len(cat)} global defects, {sum(len((p.get('defects',{}) or {})) for p in C.list_parts())} part defects.")
    return 0

if __name__=="__main__": raise SystemExit(main())
