# Grounding Reference Images

This directory is the visual specification for grounding decisions.

## Purpose

Reference images are curated examples, especially boundary cases. They are not a replacement for the grounding rules; they are evidence for what those rules mean visually.

For each category, keep examples under:

- `<category>/defect/`
- `<category>/clear/`
- `<category>/review/` when applicable

For face-dependent checks, keep the orientation examples under:

- `bracket/face/front/`
- `bracket/face/back/`
- `bracket/face/review/`

## Curation rules

1. Prefer a small set of representative and boundary examples.
2. Keep the original image and, when available, the human-annotated version together.
3. Do not add an image merely because the model made a mistake; add it when it teaches a stable visual boundary.
4. Human annotation is the expected decision, not model output.
5. Do not change grounding prose just to fit one image. First compare the image against the existing rule and reference set.
6. If a new example contradicts the established boundary, update the rule deliberately and record why.

## Current priority set

- bracket/serration
- bracket/embossing_missing
- bracket/incomplete_embossing
- bracket/line_mark
- bracket/dark_spot
- bracket/corrosion

The actual image files should be added after the user uploads the selected originals/annotations.