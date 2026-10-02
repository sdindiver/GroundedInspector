# Bearing Cup — validated ground truth & calibration answer key

> Durable memory for the **Bearing Cup** part. Read this together with
> `grounding/parts/bearing_cup.json` and `AGENTS.md` before inspecting bearing cups, so
> verdicts reproduce exactly. This is the human/QMS ground truth we grounded to.

Source of truth: QMSInspector `inspection_state/reviews/bearing_cup.json` (human labels,
already in verdict shape: `category`, `seg`, `bbox`, `location`, `reason`). Golden
reference images live in `grounding/references/parts/bearing_cup/golden/`.

## Part anatomy (the anchor)

A round, **deep-drawn metal cup**, photographed top-down (rim visible as a ring) or
tilted (shallow cylinder, rim foreshortened). Concentric features:
- **outer flange / rolled edge** (the widest rim),
- a stepped **inner rim / collar**,
- a **central bore** (through-hole) — punched open on a good part.

NOT an elongated strap and NO in-line row of holes / serrated hole (that is the
Bracket). Find the circular silhouette and the concentric rings first.

## Answer key — all 18 source images

| # | Image suffix (IMG20260824…) | result | primary category |
|---|---|---|---|
| 000 | 161444 | DEFECT | dent |
| 001 | 161503 | DEFECT | dent |
| 002 | 161530 | DEFECT | dent |
| 003 | 161547 | DEFECT | dent |
| 004 | 161557 | DEFECT | dent |
| 005 | 161920 | DEFECT | out_of_round |
| 006 | 162037 | DEFECT | missing_punch |
| 007 | 162142 | DEFECT | edge_chip |
| 008 | 162258 | DEFECT | edge_chip |
| 009 | 162340 | DEFECT | edge_chip |
| 010 | 162425 | DEFECT | edge_chip |
| 011 | 162618 | OK | — |
| 012 | 162707 | DEFECT | corrosion |
| 013 | 162751 | OK | — |
| 014 | 162819 | OK | — |
| 015 | 162900 | OK | — |
| 016 | 163000 | OK | — |
| 017 | 163031 | OK | — |

Totals: **12 DEFECT, 6 OK.** By category: dent 5, edge_chip 4, out_of_round 1,
missing_punch 1, corrosion 1, OK 6.

## Reference images used for grounding

- golden (clean OK cups): 162751, 162900, 163031 → `grounding/references/parts/bearing_cup/golden/`
- missing_punch exemplar: 162037 → `grounding/references/parts/bearing_cup/defects/missing_punch/`
- out_of_round exemplar: 161920 → `grounding/references/parts/bearing_cup/defects/out_of_round/`

## Decisive visual cues (calibration)

- **missing_punch** (severity 5, PRIMARY) — the central bore is **absent**: a solid,
  blind face where a clean through-hole should be. Compare against a golden cup whose
  bore is open. Highest priority — never miss it.
- **out_of_round** (severity 4) — the bore is not a clean circle: one side pinched,
  flattened or dented **inward** (ovalised). Judge the bore outline, not surface shine.
- **dent** (severity 4) — metal pushed in but **intact** (no missing material). Often
  an eye-shaped fold on the inner collar rim or a pushed-in flange arc. TIGHT bbox on
  the actual deformation, not the whole rim.
- **edge_chip / Edge Cut** (severity 4) — a clean sheared notch / chipped section on the
  outer flange edge where material is **MISSING** (a break in the smooth circular
  silhouette). Missing material distinguishes it from a dent.
- **corrosion** (severity 2) — brown/orange rust staining with a rough, blotchy texture;
  distinguish from plating tint or shadow. Drawn as an organic rust-segmented outline.
- **OK** — clean cup, open round bore, smooth flange and rim. Tilted / side-view cups
  whose inner rim is smooth and not clearly visible are OK — do **NOT** paint a
  speculative box; a false mark is worse than none.

## Marking parity (how QMS draws each)

QMS uses the review polygon/bbox with per-category segmentation. In GroundedInspector
`renderer.py` the category → segmentation map reproduces this:
`missing_punch/out_of_round/dent/edge_chip → edge`, `corrosion → rust`. Keep the bbox
TIGHT on the actual defect (config ruling), and the renderer traces the organic outline.

## Robustness note

QMS keeps an augmented bearing-cup set under
`inspection_state/augmented/bearing_cup_aug/` (rotations 0–315° + flips). Because the
grounding anchors on anatomy (round cup, concentric rings, open bore) and defect
signatures — not memorised pixels — verdicts hold across orientation and flips.

Known hard cases: tilted side-views where the inner rim is only partly visible (do not
false-flag a dent/out_of_round on a smooth rim → prefer OK / NEEDS_REVIEW), and faint
**corrosion** vs plating tint (require rough blotchy warm texture).
