# Bracket — validated ground truth & calibration answer key

> Durable memory for the **Bracket** part. Read this together with
> `grounding/parts/bracket.json` and `AGENTS.md` before inspecting brackets, so
> verdicts reproduce exactly. This is the human/QMS ground truth we grounded to.

Source of truth: QMSInspector `inspection_state/reviews/bracket.json` (human labels)
and `knowledge/rules/bracket.json` (taxonomy). Original (non-augmented) source
images live in `QMSInspector/inspection_jobs/QMS-20260919-150505/in/`.

## Part anatomy (the anchor)

Flat stamped steel strap, **exactly 3 holes**:
- two **plain** smooth-bore holes,
- one **serrated** (cog/scallop-toothed) hole ← the anatomical anchor; find it first.

`VA` is embossed between the middle hole and the plain end-hole, on the side of the
middle hole **opposite** the serrated hole.

## Answer key — all 22 source images

| # | Image suffix (IMG20260824…) | result | primary category |
|---|---|---|---|
| 000 | 163734 | DEFECT | line_mark |
| 001 | 163740 | DEFECT | line_mark |
| 002 | 163750 | DEFECT | line_mark |
| 003 | 163810 | DEFECT | line_mark |
| 004 | 163907 | DEFECT | serration_missing |
| 005 | 164017 | DEFECT | serration_missing |
| 006 | 164116 | DEFECT | incomplete_embossing |
| 007 | 164209 | OK | — |
| 008 | 164314 | OK | — |
| 009 | 164330 | OK | — |
| 010 | 164359 | OK | — |
| 011 | 164510 | DEFECT | line_mark |
| 012 | 164631 | DEFECT | serration_missing |
| 013 | 164648 | DEFECT | serration_missing |
| 014 | 164704 | DEFECT | serration_missing |
| 015 | 164818 | DEFECT | dark_spot |
| 016 | 164838 | DEFECT | dark_spot |
| 017 | 164950 | DEFECT | dark_spot |
| 018 | 165050 | DEFECT | dark_spot |
| 019 | 165106 | DEFECT | dark_spot |
| 020 | 165152 | DEFECT | dark_mark |
| 021 | 165247 | DEFECT | white_mark |

Totals: **18 DEFECT, 4 OK.** By category: line_mark 5, serration_missing 5,
dark_spot 5, incomplete_embossing 1, dark_mark 1, white_mark 1, OK 4.

## Reference images used for grounding

- golden: 164314, 164330, 164359  → `grounding/references/parts/bracket/golden/`
- serration_missing exemplar: 163907 → `grounding/references/parts/bracket/defects/serration_missing/`
- incomplete_embossing exemplar: 164116 → `grounding/references/parts/bracket/defects/incomplete_embossing/`
- line_mark exemplar: 163734 → `grounding/references/global/line_mark/`
- dark_spot exemplars: 164818, 164838, 164950, 165050, 165106 → `grounding/references/global/dark_spot/` (confident 164950/165106 + faint 164818/164838/165050 to anchor the threshold; plus tight localization CROPS 164818_crop, 165050_crop centered on the faint spot. 164838 has no crop — its spot is too faint to crop without misleading, so only its whole image anchors it.)
- dark_mark exemplar: 165152 → `grounding/references/global/dark_mark/`
- white_mark exemplar: 165247 → `grounding/references/global/white_mark/`

## Decisive visual cues (calibration)

- **serration_missing** — the designated serrated hole shows a **smooth circular
  rim** identical to the plain holes (no scallops). Decide by the **rim outline**,
  NOT bore brightness; glare whitens good serrated bores too. If glare makes the rim
  unreadable → NEEDS_REVIEW, don't guess.
- **incomplete_embossing** — `VA` present but one character clearly shallower/fainter
  than the other (or both washed-out shallow). Rule out glare first.
- **embossing_missing** — `VA` zone entirely blank (rule out glare/shadow/crop).
- **line_mark** — long, thin, continuous trace spanning much of the part, crossing
  holes without breaking. Short/localized = scratch (not line_mark).
  - **BRUSHED-FINISH GRAIN TRAP (learned from 163734).** This part's face is covered
    in diagonal brush grain plus many BRIGHT polish micro-streaks. Do **NOT** pick the
    brightest/shiniest streak — that is polish/grain, not the defect. The genuine
    line_mark on 163734 is a **single continuous diagonal groove running from just right
    of the middle hole down to the serrated hole** — user-validated at line
    ≈ `0.577,0.512 → 0.377,0.882` (display-normalized). It runs at a *similar* angle to
    the grain, so identify it by **continuity + singularity + definition** (one unbroken
    groove spanning much of the part, faint but more defined than the shallow grain),
    NOT by maximum brightness and NOT by angle. The engine's first (wrong) mark grabbed
    the brighter parallel polish streak to the right (~`0.65,0.49 → 0.42,0.80`). Encoded
    durably in `grounding/defects.json` → `line_mark.finish_grain_rule` (pinned in
    `grounding/required_grounding.json`).
- **dark tiers (TWO only)** — dark_spot → dark_mark. dark_mark =
  discrete near-black solid blotch; dark_spot = a few small rounded darker spots
  (what earlier notes called "speckling" is a dark_spot; there is no dark_speckling category).
- **white_mark** — localized **duller / less reflective** patch, brushed grain still
  visible, angle-stable. NOT glare (brighter + grain-free) and NOT the uniform
  whole-face rainbow passivation tint.

## Robustness (proves no training needed)

Blind-tested on QMS augmented set `inspection_state/augmented/bracket_line_mark/`
(426 imgs: rotation 0–360°, H/V flips, brightness/contrast/gamma, lighting gradient,
noise). Results: **22/22** original + **11/11** first augmented sample + **22/22**
fresh augmented sweep = **55/55 correct**, all defect types, every orientation.

Known hard cases: bright washed-out **164017** (serration_missing — QMS's shipped
output marks the smooth-rimmed bottom hole; read the rim outline, not bore glare), and
**165247 white_mark** (subtle; apply dull-vs-glare test).
