# GroundedInspector project rules

This file is the working authority for the repository.

## Project principle

Keep the project minimal and auditable:

- One concept has one authoritative rule.
- Every configuration field must have a runtime consumer.
- Do not add aliases, duplicate identity metadata, "do not confuse" lists, parallel rule fields, or speculative configuration.
- Part selection uses the canonical part name and filename.
- Defect decisions live in `grounding/defects.json` or the owning part file.
- `inspect.config` is runtime production configuration only; grounding rules must not depend on it.

## Current architecture

```
grounding/
  system_prompt.md
  defects.json
  parts/<part>.json
  references/

grounded_inspector/
  loader.py
  assembler.py
  inspection/
    transport.py
    anatomy.py
    defect.py
    aggregator.py
    pipeline.py
  inspect.py
  renderer.py

tools/
  check_grounding.py
```

Runtime path for explicit-part inspection:

```
loader -> assembler -> shared anatomy -> independent defect inspectors -> aggregator -> renderer
```

The modular inspection pipeline is the production path for inspection runs:
- explicit-part runs establish shared anatomy once, then evaluate every configured defect independently;
- auto-identification first finds each configured part instance, then sends each identified instance through the same shared-anatomy and independent-defect stages;
- verdict aggregation is deterministic;
- the renderer displays the aggregated verdict and must not semantically reclassify defects.

## Grounding schema

A part file contains only:

- `schema_version`
- `part`
- `description`
- `anatomy`
- `inspection`
- `golden_images`
- `defects`

The filename is the canonical identifier. For example:

- `grounding/parts/bracket.json` -> `Bracket`
- `grounding/parts/bearing_cup.json` -> `Bearing Cup`

Do not add aliases or a second identity structure.

A defect contains only authoring fields:

- `severity`
- `display_name`
- `color`
- `decision`

The loader derives runtime scope and reference paths. Defect annotation shape is not authored; rendering behavior is derived from the category.

Each decision owns:

- `check`
- `defect_when`
- `clear_when`
- `review_when`
- `ignore`
- `boundary` when needed
- `enumeration` when multiple instances matter
- `localization`

## Inspection discipline

- Use visible evidence only.
- Establish required anatomy/orientation before dependent checks.
- Run every item in the inspection plan.
- Do not use glare, reflection, normal finish, shadow, or explicit IGNORE evidence as defect evidence.
- Enumerate every distinct actionable defect.
- Use NEEDS_REVIEW only when the owning rule says required evidence is insufficient.
- Localize reported defects tightly to the actual defective feature.
- Never invent a defect category outside the resolved catalog.
- A rendering fix belongs in `renderer.py`; a classification/localization rule belongs in `grounding/`.

## Image inspection

When inspecting a user-provided image:

1. Inspect only the named image unless the user explicitly requests a set.
2. Judge the image visually from the grounding bundle.
3. Do not use detection code to find defects.
4. Place coordinates from the visible anatomy/defect location.
5. Render once, then visually check the rendered result.
6. Do not use answer keys as inspection input.

## Validation

After grounding changes run:

```
python -m tools.check_grounding
```

It must pass.

Do not claim a visual result was tested unless the image was actually inspected/rendered.

## Authoring rule

If a field has no current runtime consumer, remove it instead of documenting it as "future use".

If two fields express the same concept, keep the one that is actually consumed and delete the duplicate.

Do not preserve legacy configuration merely for compatibility unless the repository currently has a real caller that requires it.
