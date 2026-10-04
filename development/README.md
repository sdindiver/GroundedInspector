# GroundedInspector

Scalable, **grounded** visual defect inspection — no per-part model training. Each image is
inspected by comparing it to a **golden reference** + **few-shot defect exemplars** + a
**canonical defect catalog**; a vision model (Claude in the IDE now, the Anthropic Vision
API later) returns a JSON verdict, and the renderer draws it.

> **New session:** read **[`AGENTS.md`](../AGENTS.md)** at the repo root — it is the
> authoritative operating guide (invariants, fix-routing, how to add a part).

## Project structure

- **`grounding/`** — the BUNDLE (everything the API reads):
  - `system_prompt.md` — universal inspection discipline + output shape
  - `defects.json` — global defect catalog (shared by every part)
  - `parts/<part>.json` — per-part identity, part-specific defects, rulings
  - `references/` — golden + few-shot defect exemplar images
  - `required_grounding.json` — the build-time GATE (read only by `check_grounding.py`,
    **not** sent to the API): pins concepts that must reach the prompt, by reference to the
    owning field so no rule text is duplicated
- **`grounded_inspector/`** — the code: `loader.py` (load grounding), `assembler.py`
  (build the prompt bundle), `renderer.py` (draw verdicts)
- **`tools/check_grounding.py`** — the grounding gate; must print **PASSED** after any
  grounding change
- **`development/`** — dev/operator reference, never shipped to the API (this folder;
  `docs/grounding/*_ground_truth.md` = validated answer keys / regression baseline)

## Two kinds of defect

| Kind | Where | Applies to |
|---|---|---|
| **Global** | `grounding/defects.json` | every part (`scope:"all"`) |
| **Part-specific** | `grounding/parts/<part>.json` | one part |

## Add a part

See **AGENTS.md → "ADDING A NEW PART"**. In short: create `grounding/parts/<part>.json`,
drop a golden + one exemplar per defect under `grounding/references/parts/<part>/`, then:

```
python -m tools.check_grounding   # must print PASSED
```
