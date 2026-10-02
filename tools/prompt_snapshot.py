"""P0 safety net: snapshot the fully-rendered prompt and diff against a frozen golden.

WHY: the grounding JSON IS the prompt (the renderer prints keys as headings and values
verbatim). So ANY edit to grounding/ can silently change what the model sees. This tool
renders the complete prompt for every part (single-part AND auto mode) and compares it to a
frozen snapshot, so an offline edit is instantly verified:
    - "prompt unchanged" -> your edit was purely structural/behavior-preserving, or
    - a unified diff showing the EXACT lines that changed -> you changed what the model sees.

USAGE:
    python -m tools.prompt_snapshot            # diff current render vs golden (exit 1 if changed)
    python -m tools.prompt_snapshot --update   # (re)freeze the golden snapshots

Run the diff after ANY grounding edit. If you INTENDED to change behavior, re-run --update to
accept the new golden; if you did NOT, the diff tells you what to revert.
"""
from __future__ import annotations

import argparse
import difflib
import glob
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from grounded_inspector import assembler as G  # noqa: E402
from grounded_inspector import loader as C  # noqa: E402

SNAP_DIR = os.path.join(HERE, "tools", "prompt_snapshots")

# A FIXED input image so the snapshot is deterministic (the prompt only references the path,
# the grounding content is what we are guarding). Must exist so build warnings are stable.
def _fixed_image() -> str:
    refs = sorted(glob.glob(os.path.join(HERE, "grounding", "references", "**", "*.jpg"), recursive=True))
    return refs[0] if refs else os.path.join(HERE, "grounding", "references", "_fixed.jpg")


def _render_all() -> dict:
    """name -> rendered prompt text, for every part (single) plus auto mode."""
    img = _fixed_image()
    out = {}
    for cfg in C.list_parts():
        part = cfg.get("part")
        stem = str(part).strip().lower().replace(" ", "_")
        out[f"{stem}.single"] = G.render_prompt(G.build_bundle(part, img))
    out["auto"] = G.render_auto_prompt(G.build_auto_bundle(img))
    return out


def _snap_path(name: str) -> str:
    return os.path.join(SNAP_DIR, f"{name}.txt")


def update() -> int:
    os.makedirs(SNAP_DIR, exist_ok=True)
    rendered = _render_all()
    for name, text in rendered.items():
        with open(_snap_path(name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    print(f"Froze {len(rendered)} golden prompt snapshot(s) in {os.path.relpath(SNAP_DIR, HERE)}:")
    for name in sorted(rendered):
        print(f"  - {name}.txt")
    return 0


def diff() -> int:
    rendered = _render_all()
    changed = []
    for name, text in sorted(rendered.items()):
        path = _snap_path(name)
        if not os.path.isfile(path):
            print(f"  ! no golden snapshot for '{name}' - run --update to create it.")
            changed.append(name)
            continue
        with open(path, "r", encoding="utf-8") as fh:
            golden = fh.read()
        if golden != text:
            changed.append(name)
            d = difflib.unified_diff(golden.splitlines(), text.splitlines(),
                                     fromfile=f"golden/{name}", tofile=f"current/{name}", lineterm="")
            print(f"\n=== PROMPT CHANGED: {name} ===")
            for ln in d:
                print(ln)
    if changed:
        print(f"\nPROMPT SNAPSHOT DIFF: {len(changed)} prompt(s) changed: {', '.join(sorted(changed))}.")
        print("If this change was INTENTIONAL, run:  python -m tools.prompt_snapshot --update")
        print("If NOT, your edit altered what the model sees - revert the lines shown above.")
        return 1
    print(f"PROMPT SNAPSHOT OK: all {len(rendered)} rendered prompt(s) are byte-identical to golden.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Snapshot/diff the fully-rendered grounding prompt.")
    ap.add_argument("--update", action="store_true", help="(re)freeze the golden snapshots")
    args = ap.parse_args()
    return update() if args.update else diff()


if __name__ == "__main__":
    raise SystemExit(main())
