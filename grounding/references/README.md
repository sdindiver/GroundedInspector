# Grounding Reference Images

This directory is the visual specification for grounding decisions.

## Purpose

Reference images are curated examples, especially boundary cases. They are not a replacement for the grounding rules; they are evidence for what those rules mean visually.

References may be organized by scope:

- `global/<category>/` for rules that apply across parts.
- `parts/<part>/<category>/` for part-specific rules.

Within a category, keep the original image and, when available, its cropped/annotated companion together. The manifest records the expected decision and points to the image, crop, and human annotation.

For face-dependent checks, keep orientation examples under:

- `parts/<part>/face/front/`
- `parts/<part>/face/back/`
- `parts/<part>/face/review/`

## Curation rules

1. Prefer a small set of representative and boundary examples.
2. Keep the original image and, when available, the human-annotated version together.
3. A cropped image is supporting visual context; the original remains the authoritative source image.
4. Do not add an image merely because the model made a mistake; add it when it teaches a stable visual boundary.
5. Human annotation is the expected decision, not model output.
6. Do not change grounding prose just to fit one image. First compare the image against the existing rule and reference set.
7. If a new example contradicts the established boundary, update the rule deliberately and record why in the manifest/annotation.

## Current reference set

The currently registered reference set includes the existing global dark-spot examples:

`global/dark_spot/`

The five examples cover:

- a faint edge-hugging dark smudge that is still a reportable dark spot;
- a bounded dark spot beside the VA emboss;
- multiple independent dark spots that must be enumerated;
- darker-than-finish spots that are not passivation tint or hole shadow;
- discrete dark mottling that remains distinct from overall surface tint.

See `reference_manifest.json` for the machine-readable index.

## Adding references

When adding a reference:

1. Preserve the original image.
2. Add a crop when it materially helps show the decision boundary.
3. Add a short human annotation describing the expected classification and why nearby lookalikes are excluded.
4. Register the reference in `reference_manifest.json`.
5. Do not duplicate an existing reference merely because it came from a different inspection run.
