"""SessionStart hook entry point.

Runs the grounding gate before an agent session continues.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from tools.check_grounding import main as gate_main


def run() -> int:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = gate_main()
    output = buf.getvalue()

    message = (
        "Grounding session gate ran. Follow AGENTS.md as the project authority.\n\n"
        + output
    )

    if code != 0:
        print(json.dumps({
            "continue": False,
            "stopReason": "Grounding gate FAILED - fix grounding/ before continuing.",
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
