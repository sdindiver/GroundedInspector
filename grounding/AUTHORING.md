# Grounding authoring guide

The grounding has one rule owner per concept. Keep the part schema minimal: every field must have a runtime purpose.

## Files

- `system_prompt.md` — universal model behavior and output contract.
- `defects.json` — one canonical decision for each global defect.
- `parts/<part>.json` — canonical part name, description, anatomy, inspection order, references, and part-specific defects.
- `references/` — visual examples only.
- `tools/check_grounding.py` — structural validator.

## Part schema

A part contains only:

- `schema_version`
- `part`
- `description`
- `anatomy`
- `inspection`
- `golden_images`
- `defects`

The part filename is its canonical identifier. Do not add aliases, identity summaries, "do not confuse" metadata, or other duplicate identification fields.

## Defect template

Every defect uses the same decision shape:

    {
      "severity": 3,
      "display_name": "Human name",
      "scope": "all | part",
      "decision": {
        "check": "What to inspect.",
        "defect_when": "Evidence that confirms the defect.",
        "clear_when": "Evidence that confirms the feature is normal.",
        "review_when": "Evidence is insufficient or competing states cannot be separated.",
        "ignore": ["Evidence that must not be used."],
        "boundary": "How this defect differs from its closest competing defect.",
        "enumeration": "How multiple instances are counted.",
        "localization": "Where the bbox goes."
      }
    }

`reference_dir` and `annotation` are optional only when the runtime actually needs them.

## Ownership rules

1. A decision belongs in exactly one defect.
2. Universal evidence rules belong in `system_prompt.md`.
3. Part anatomy belongs in the part's `anatomy`.
4. Inspection order belongs in the part's `inspection`.
5. Do not add metadata that repeats another field or has no runtime consumer.
6. Do not encode important current rules only in historical notes.
7. When a miss is found, strengthen the existing decision or add a test/example; do not create a parallel exception.
8. `NEEDS_REVIEW` is the explicit outcome when required evidence cannot distinguish the allowed states.

Run `python -m tools.check_grounding` before committing grounding changes.
