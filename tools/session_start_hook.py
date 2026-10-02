"""SessionStart hook entry point.

Runs the grounding gate (tools.check_grounding) at the start of every agent session and
injects its STRICT DISCIPLINE contract into the session context via the hook JSON contract.
If the gate fails, the hook blocks (exit 2) so no work starts on a broken bundle.

This is the deterministic enforcement layer: it fires without relying on the agent choosing
to run the gate. Keep it small and auditable.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from tools.check_grounding import main as gate_main  # noqa: E402


def run() -> int:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = gate_main()
    output = buf.getvalue()

    message = (
        "GroundedInspector session gate ran. AGENTS.md is the ONLY authority - obey it EXACTLY, "
        "even under task pressure. The recurring failure is skipping a rule that is already "
        "written; do not do that.\n\n" + output
    )

    if code != 0:
        print(json.dumps({
            "continue": False,
            "stopReason": "Grounding gate FAILED - fix the bundle (config/ or AGENTS.md) before any work.",
            "systemMessage": message,
        }))
        return 2

    print(json.dumps({
        "hookSpecificOutput": {"hookEventName": "SessionStart"},
        "systemMessage": message,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
