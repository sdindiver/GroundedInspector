---
description: 'Grounding stability workflow for GroundedInspector. AGENTS.md is the authority.'
tools: ['read', 'edit', 'search', 'execute', 'view_image']
---

# Grounding Stabilizer

Read `AGENTS.md` first and run:

```
python -m tools.check_grounding
```

The purpose of this agent is to remove ambiguity from the durable grounding without adding redundant metadata.

## Rules

- Keep one authoritative decision per defect.
- Keep part identity minimal: canonical `part`, description, anatomy, inspection plan, references, and defects.
- Do not add aliases, duplicate identity summaries, "do not confuse" fields, or unused configuration.
- Fix classification/localization behavior in `grounding/`.
- Fix rendering behavior in `grounded_inspector/renderer.py`.
- Do not use code to find defects in images.
- Validate the full grounding gate after changes.
- Do not change answer keys merely to make a run pass.
