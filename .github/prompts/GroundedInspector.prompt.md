---
mode: agent
description: GroundedInspector session — follow AGENTS.md.
---

# GroundedInspector

1. Read `AGENTS.md`.
2. Run `python -m tools.check_grounding`.
3. Follow the current `grounding/` schema and inspection rules.
4. Keep the project minimal: every field must have a runtime purpose.
5. Do not introduce aliases, duplicate identity metadata, or unused configuration.
6. Do not use `inspect.config`.
7. Inspect only the image scope requested by the user.
8. Keep business rules in `grounding/`; keep drawing behavior in `grounded_inspector/renderer.py`.
