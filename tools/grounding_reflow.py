"""P2 migration: reflow long run-on rule strings into diff-able SENTENCE ARRAYS.

Turns a 1,800-char wall like  "A. B. C. ..."  into  ["A.", "B.", "C.", ...]  which the
renderer joins back with a single space (see assembler._prose) to the IDENTICAL string. This
only makes the JSON human-editable - it does NOT change the rendered prompt (verify with
tools.prompt_snapshot).

SAFETY: a string is converted ONLY when the split rejoined with " " equals the original
byte-for-byte. Fields the renderer prints DIRECTLY (not via _prose) are never touched:
`signature` (defect header) and any dict (annotation, confidence_model). Idempotent.

    python -m tools.grounding_reflow            # dry-run: list what would change
    python -m tools.grounding_reflow --write    # apply, then run tools.prompt_snapshot
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GROUNDING = os.path.join(HERE, "grounding")

# Rendered directly (not through _prose) -> must stay a plain string.
_NEVER = {"signature"}
_MIN_LEN = 240  # only reflow the genuine run-on walls
_SPLIT = re.compile(r'(?<=[.:?!]) (?=[A-Z("\'])')  # split at a single space after . : ? !


def _to_sentences(s: str):
    """Return a sentence list whose ' '.join is byte-identical to s, or None if not splittable."""
    if not isinstance(s, str) or len(s) < _MIN_LEN:
        return None
    parts = _SPLIT.split(s)
    if len(parts) > 1 and " ".join(parts) == s:
        return parts
    return None


def _reflow_value(key, val, changes, ctx):
    if key in _NEVER or not isinstance(val, str):
        return val
    parts = _to_sentences(val)
    if parts:
        changes.append(f"{ctx}.{key}  ({len(val)} chars -> {len(parts)} sentences)")
        return parts
    return val


def _reflow_defectmap(defmap, changes, ctx):
    for cat, spec in (defmap or {}).items():
        if not isinstance(spec, dict):
            continue
        for k in list(spec.keys()):
            spec[k] = _reflow_value(k, spec[k], changes, f"{ctx}.{cat}")


def _reflow_list(items, changes, ctx):
    for i, it in enumerate(items or []):
        if isinstance(it, str):
            parts = _to_sentences(it)
            if parts:
                changes.append(f"{ctx}[{i}]  ({len(it)} chars -> {len(parts)} sentences)")
                items[i] = parts


def _process_file(path, changes):
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    rel = os.path.relpath(path, HERE)
    if os.path.basename(path) == "defects.json":
        _reflow_defectmap(data.get("defects"), changes, f"{rel}:defects")
    else:  # a part config
        _reflow_defectmap(data.get("part_defects"), changes, f"{rel}:part_defects")
        if isinstance(data.get("rulings"), list):
            _reflow_list(data["rulings"], changes, f"{rel}:rulings")
        if isinstance(data.get("notes"), list):
            _reflow_list(data["notes"], changes, f"{rel}:notes")
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description="Reflow run-on rule strings into sentence arrays.")
    ap.add_argument("--write", action="store_true", help="apply changes (default: dry-run)")
    args = ap.parse_args()

    files = [os.path.join(GROUNDING, "defects.json")]
    files += sorted(glob.glob(os.path.join(GROUNDING, "parts", "*.json")))

    total = 0
    for path in files:
        changes = []
        data = _process_file(path, changes)
        total += len(changes)
        for c in changes:
            print(("WRITE " if args.write else "would ") + c)
        if args.write and changes:
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
    print(f"\n{'Reflowed' if args.write else 'Would reflow'} {total} field(s).")
    if args.write:
        print("Now run:  python -m tools.prompt_snapshot   (must be byte-identical)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
