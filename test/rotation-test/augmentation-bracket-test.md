# Augmentation / Rotation Robustness Test — Bracket

**How to run:** open a NEW session and say *"Read `c:\workspace-ai\GroundedInspector\test\rotation-test\augmentation-bracket-test.md` and do what it says."*

This test checks that defect **detection AND location** survive when the part is rotated to
arbitrary angles — i.e. that the grounding (not memorised pixels or prior chat) drives the
result. It must behave the way the production **Anthropic Vision API** would.

---

## 0. Bootstrap (do first)
1. Read `c:\workspace-ai\GroundedInspector\AGENTS.md` and follow it.
2. Run `python -m tools.check_grounding` → it MUST print **PASSED**. If not, stop and fix
   `grounding/` before continuing.

## 1. Rules of the test (production-faithful — non-negotiable)
- Inspect **BLIND & VISUAL** per AGENTS.md INVARIANT 0c:
  - Find the part's **anatomy anchor** (the SERRATED hole = the largest hole) at its new,
    rotated orientation, and locate everything relative to it — never "top/left of image".
  - Apply ONLY the `grounding/` rules + what you can SEE. Zoom into suspect regions.
  - **Do NOT** run OpenCV / ridge / LSD / any code to FIND a defect (the API can't).
  - **Do NOT** open the answer keys in `development/docs/grounding/` — that is checking, not
    inspecting. Work only from `AGENTS.md` + `grounding/` + the image pixels.
- Do not rely on any prior conversation or memory for the ANSWER; the judgement must come
  from the grounding applied to the rotated pixels.
- **IGNORE saved agent memory for this test.** Do NOT consult `/memories/repo/line_mark_lessons.md`
  or any other saved memory when deciding a verdict. The production Anthropic Vision API has
  NO memory — it sees only the bundle + image. So inspect using ONLY the `grounding/` rules
  and what you can see. (Reading `AGENTS.md` for the invariants/output convention is fine; it
  is process discipline, not defect answers.) If a rule you "remember" is not present in
  `grounding/`, do NOT use it — that would be cheating the test.

## 2. Build the rotated test set
Source images (known-defect brackets) in `c:\workspace-ai\images_640\bracket\`:
- `IMG20260824163907_640.png`  (serration_missing)
- `IMG20260824164818_640.png`  (dark_spot)
- `IMG20260824165152_640.png`  (dark_mark)
- `IMG20260824164116_640.png`  (incomplete_embossing)

For each, create a rotated copy at a DIFFERENT **random arbitrary angle** (NOT 90/180 —
e.g. 37°, 118°, 203°, 291°), and additionally **mirror** one of them. Expand the canvas so
the part is never clipped (rotate with `expand=True`, pad background). Save each rotated copy
as `<name>_rot<angle>.png` (or `<name>_mirror.png`) into:
`c:\workspace-ai\images_640\bracket\rotation_test\`
(rotating/mirroring an image is allowed — that is preparing the test, not finding a defect.)

## 3. Inspect each rotated image and report TWO things

### ⚡ ONE-PASS RULE (do this per image — do NOT loop code + re-render)
The endless "edit coords → re-render → still wrong → edit again" churn is caused by writing
a bbox you have not LOOKED at. Prevent it:
1. **VIEW the rotated image FIRST.** Find the anatomy anchor (serrated = largest hole), then
   read where the defect sits relative to it. Do NOT write any bbox before you have seen it.
2. **Place the box by eye, once**, from that anchor (largest hole / strap edge / VA zone).
   Do NOT use OpenCV/HoughCircles/heuristics to FIND it — that drifts and forces re-tuning.
3. **Render once, then VIEW the annotated output once.** If the mark sits on the feature,
   that image is DONE — move on. Only re-touch an image whose mark you actually saw is off.
4. If the terminal errors with `SyntaxError`/`>>>` it is a Python REPL, not a shell — STOP
   and get a clean PowerShell (see AGENTS.md STOP section). Never tune coords blind.

For every rotated image, output:
- **INPUT (expected):** the defect it should still be, and WHERE it should appear now, in
  anatomy terms (e.g. "serration_missing on the largest hole"; "dark_spot on the strap edge
  between the two smaller holes"). This is what a correct result looks like after that rotation.
- **OUTPUT (detected):** what you actually detect + where you mark it, judged only from the
  rotated pixels + grounding. Note confidence and whether you used a region-box + NEEDS_REVIEW.

## 4. Draw the results (PAIRED next-next viewing — one folder)
- First DELETE the entire `rotation_test\` folder if it exists, then recreate it fresh.
- Put BOTH the rotated original AND its annotated copy in the SAME folder
  `c:\workspace-ai\images_640\bracket\rotation_test\`, named so they sort ADJACENTLY:
    - original:  `<name>_rot<angle>.png`  (or `<name>_mirror.png`)
    - annotated: `<name>_rot<angle>_ANNOTATED.png`
  so an image viewer shows original -> its annotated -> next original -> ... on next-next.
- Draw with `grounded_inspector/renderer.py` (region box / tight box per defect).
- For this test do NOT use an `annotated/` subfolder, and do NOT create a `runs/` folder.

## 5. Final verdict (the point of the test)
For each image state clearly:
- Did **DETECTION** survive rotation? (same defect found — yes/no)
- Did **LOCATION** survive rotation? (marked on the correct anatomy — yes/no)
- If either broke, say exactly where the anatomy-anchor or localization failed.

Then one honest summary line: does the grounding hold under arbitrary rotation, and where is
it weakest (expected weak spot: precise placement of faint/small defects, which is
orientation-independent, not the rotation itself).
