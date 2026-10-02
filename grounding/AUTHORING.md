# Grounding authoring guide — how to add/edit rules safely

This is an **operator doc**. It is NOT sent to the API (the renderer only reads
`system_prompt.md`, `defects.json`, `parts/*.json`, `rules.json`, and the `references/`
images). Editing this file never changes behavior.

## The one rule that makes editing safe
**The grounding JSON *is* the prompt.** The renderer prints each field key as a HEADING and
each value verbatim, in order. So any content edit can change what the model sees. Before and
after every edit, run the snapshot guard:

```
python -m tools.prompt_snapshot          # "byte-identical" = you changed nothing the model sees
python -m tools.prompt_snapshot --update # accept a NEW golden (only when you INTEND a change)
python -m tools.check_grounding          # must print PASSED
```

If the diff shows lines you did not mean to change, revert them. If you intended the change,
`--update` accepts the new golden — and if it changes the *model's behavior*, re-validate the
verdicts (run `grounded_inspector.inspect` on your test images) before trusting it.

## Where does a rule go? (decision table)
| You want to… | Put it here | Renders as |
|---|---|---|
| A rule for **every part** (universal discipline, output schema) | `grounding/system_prompt.md` | prose in the system prompt |
| Define/limit a **global defect** (applies to all parts) | `grounding/defects.json` → `defects.<cat>` | `- **<cat>** …: <signature>` + one line per guidance field |
| A **part-specific** defect or ruling | `grounding/parts/<part>.json` → `part_defects` / `rulings` / `notes` | same shape as global, under that part |
| A rule **shared by several parts** (author once) | `grounding/rules.json` → `rules.<id>`, then `{ "$ref": "<id>" }` where used | expands to the identical text |
| **Pin** a rule so it can never be silently dropped | `grounding/required_grounding.json` | (gate only — not sent to API) |
| Operator answer key / notes | `development/docs/…` | (never sent to API) |

## How fields render (so you edit the right thing)
- **`signature`** renders DIRECTLY in the defect header line → it must stay a **plain string**
  (never a sentence-array; the header does not join arrays).
- **Guidance fields** (`disambiguation`, `glare_rule`, `localization`, `confidence_rule`,
  `enumeration_rule`, …) render as `KEY NAME: value`. Key name = the field name, upper-cased
  with underscores→spaces. **Renaming a key changes the heading** → changes the prompt.
- **`confidence_model`** (a dict) is **NOT** rendered to the prompt — it is consumed by
  `grounded_inspector/confidence.py`. Editing it does not change what the model sees.
- **`annotation.instruction`** renders directly (as `ANNOTATION [shape]: …`) → keep it a string.
- **Order matters.** Guidance renders in JSON key order; rulings/notes in list order.
  Reordering changes the prompt.

## Authoring sugar: sentence arrays (readable, diff-able)
A long rule can be written as a **list of sentences** instead of one wall of text. The renderer
joins them with a single space, so it renders to the **identical** string:

```jsonc
"disambiguation": [
  "First sentence of the rule.",
  "Second sentence.",
  "Third sentence."
]
```

To auto-convert existing walls into sentence arrays (only when the rejoin is byte-identical):
```
python -m tools.grounding_reflow          # dry-run: preview
python -m tools.grounding_reflow --write  # apply, then run prompt_snapshot (must be identical)
```

## Shared rules (single-source): `rules.json` + `$ref`
When the same rule belongs to several parts, author it **once** in `rules.json` and reference it:

```jsonc
// grounding/rules.json
{ "rules": { "glare_bright_finish_discipline": [ "sentence 1.", "sentence 2." ] } }

// grounding/parts/bracket.json  (rulings array)
{ "$ref": "glare_bright_finish_discipline" }
```

The reference expands to the identical text at render time (confirm with `prompt_snapshot`), so
you now edit the rule in one place and every part that references it updates.

## Adding a NEW rule (the safe loop)
1. Add the rule where the decision table says (as a sentence array if it's long).
2. `python -m tools.prompt_snapshot` → review the diff (it SHOULD show exactly your new lines).
3. `python -m tools.prompt_snapshot --update` to accept it.
4. `python -m tools.check_grounding` → PASSED.
5. (If it changes the model's *decision*) re-run inspection on your test images to confirm.
6. Optionally pin it in `required_grounding.json` so it can never be dropped.

## Adding a NEW part (scale)
1. Create `grounding/parts/<part>.json` (copy `bracket.json`'s shape: `identity`,
   `part_defects`, `rulings`, `notes`).
2. Reuse cross-cutting rules via `{ "$ref": "…" }` into `rules.json` instead of re-pasting them
   (this is what keeps the bundle from ballooning as parts are added).
3. Drop exemplars under `references/parts/<part>/…`; give each a tight `_crop` + `.txt` caption
   (`python -m tools.make_exemplar_crop`).
4. `prompt_snapshot --update`, then `check_grounding` → PASSED.

## The tools at a glance
- `tools/prompt_snapshot.py` — freeze/diff the rendered prompt (**the safety net**).
- `tools/grounding_reflow.py` — turn run-on strings into sentence arrays (byte-identical).
- `tools/make_exemplar_crop.py` — generate a localization crop + caption for an exemplar.
- `tools/check_grounding.py` — the gate: every rule reaches the prompt; pins satisfied; draw
  shapes agree; plus a non-fatal note for exemplars missing a crop.
