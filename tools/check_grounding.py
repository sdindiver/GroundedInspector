"""Validate the minimal grounding schema.

This validator rejects unused/redundant configuration fields so the grounding
does not grow a second source of truth.
"""
from __future__ import annotations
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from grounded_inspector import loader as C

REQUIRED_DECISION = {"check", "defect_when", "clear_when", "review_when"}
DECISION_FIELDS = {
    "check", "defect_when", "clear_when", "review_when",
    "ignore", "boundary", "enumeration", "localization",
}
PART_FIELDS = {"schema_version", "part", "description", "anatomy", "inspection", "golden_images", "defects"}
DEFECT_FIELDS = {"severity", "display_name", "color", "scope", "reference_dir", "decision", "annotation"}
FAIL = []


def fail(msg):
    FAIL.append(msg)


def check_keys(obj, allowed, where):
    extra = set(obj) - allowed
    if extra:
        fail(f"{where}: unsupported fields {sorted(extra)}")


def check_defect(cat, spec, where):
    if not isinstance(spec, dict):
        fail(f"{where}.{cat}: must be an object")
        return
    check_keys(spec, DEFECT_FIELDS, f"{where}.{cat}")
    if not spec.get("display_name"):
        fail(f"{where}.{cat}: missing display_name")
    if "severity" not in spec:
        fail(f"{where}.{cat}: missing severity")
    dec = spec.get("decision")
    if not isinstance(dec, dict):
        fail(f"{where}.{cat}: missing decision object")
        return
    check_keys(dec, DECISION_FIELDS, f"{where}.{cat}.decision")
    missing = REQUIRED_DECISION - set(dec)
    if missing:
        fail(f"{where}.{cat}: decision missing {sorted(missing)}")
    if not isinstance(dec.get("ignore"), list):
        fail(f"{where}.{cat}: decision ignore must be a list")
    if not (dec.get("localization") or spec.get("annotation")):
        fail(f"{where}.{cat}: missing localization")
    if spec.get("scope") not in {"all", "part"}:
        fail(f"{where}.{cat}: scope must be 'all' or 'part'")
    annotation = spec.get("annotation")
    if annotation is not None:
        if not isinstance(annotation, dict):
            fail(f"{where}.{cat}: annotation must be an object")
        elif annotation.get("shape") not in {"box", "line"}:
            fail(f"{where}.{cat}: annotation.shape must be 'box' or 'line'")


def main():
    catalog = C.load_global_catalog()
    check_keys(catalog, {"schema_version", "defects"}, "global catalog")
    if catalog.get("schema_version") != 2:
        fail("global catalog: schema_version must be 2")
    cat = catalog.get("defects", {}) or {}
    ids = set()

    for name, spec in cat.items():
        if name in ids:
            fail(f"duplicate global defect: {name}")
        ids.add(name)
        check_defect(name, spec, "global")
        if isinstance(spec, dict) and spec.get("scope") != "all":
            fail(f"global catalog.{name}: global defects must use scope 'all'")

    for part in C.list_parts():
        p = part.get("part", "?")
        check_keys(part, PART_FIELDS, f"part:{p}")
        if part.get("schema_version") != 2:
            fail(f"{p}: schema_version must be 2")
        if not part.get("part"):
            fail("part: missing part name")
        if not isinstance(part.get("inspection"), list):
            fail(f"{p}: inspection must be a list")
        if not isinstance(part.get("golden_images"), list):
            fail(f"{p}: golden_images must be a list")
        defs = part.get("defects", {}) or {}
        local = set()
        for name, spec in defs.items():
            if name in local:
                fail(f"{p}: duplicate part defect {name}")
            local.add(name)
            if name in cat:
                fail(f"{p}: defect {name} duplicates a global category; keep one owner")
            check_defect(name, spec, f"part:{p}")
            if isinstance(spec, dict) and spec.get("scope") != "part":
                fail(f"part:{p}.{name}: part defects must use scope 'part'")

        plan = part.get("inspection", [])
        if not plan:
            fail(f"{p}: missing inspection plan")
        if len(plan) != len(set(plan)):
            fail(f"{p}: inspection plan contains duplicates")

        known = ids | local | set(defs)
        unknown = [x for x in plan if x not in known and x != "orientation"]
        if unknown:
            fail(f"{p}: inspection references undefined defects: {unknown}")

    if FAIL:
        print("GROUNDING VALIDATION FAILED")
        for x in FAIL:
            print("  x", x)
        return 1

    print(
        f"GROUNDING VALIDATION PASSED: {len(cat)} global defects, "
        f"{sum(len((p.get('defects', {}) or {})) for p in C.list_parts())} part defects."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
