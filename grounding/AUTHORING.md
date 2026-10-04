# Grounding authoring guide

The grounding has one rule owner per concept.

## Files

- `system_prompt.md` — universal model behavior only.
- `global_rules.json` — universal inspection/evidence rules.
- `defects.json` — one canonical decision per global defect.
- `parts/<part>.json` — part identity, anatomy, inspection order, and part-specific defects.
- `references/` — visual examples only.
- `tools/check_grounding.py` — structural validator.

## Defect template

Every defect uses the same decision shape:

    {
      "id": "defect_name",
      "severity": 3,
      "display_name": "Human name",
      "scope": "all | opt_in | part",
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

The validator requires check, defect_when, clear_when, review_when, ignore, and localization/annotation.

## Ownership rules

1. A decision belongs in exactly one defect.
2. Universal evidence rules belong in `global_rules.json`.
3. Part anatomy belongs in the part's `anatomy`.
4. Inspection order belongs in the part's `inspection`.
5. Do not add a second ruling/note that restates a defect decision.
6. Do not encode important current rules only in historical notes.
7. When a miss is found, strengthen the existing decision or add a test/example; do not create a parallel exception.
8. `NEEDS_REVIEW` is the explicit outcome when required evidence cannot distinguish the allowed states.

Run `python -m tools.check_grounding` before committing grounding changes.
