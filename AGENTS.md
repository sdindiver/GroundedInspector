# AGENTS.md — READ THIS FIRST, EVERY SESSION (GroundedInspector)

<!-- ========================================================================
     SESSION BOOTSTRAP — if you are an AI agent and just read this file,
     DO THESE STEPS NOW, before any task. This is self-executing: reading
     this file IS the instruction. The user only has to say "read AGENTS.md".
     ======================================================================== -->

## ⛔⛔ STRICT DISCIPLINE — AGENTS.md OVERRIDES YOUR REFLEXES, ALWAYS ⛔⛔
This file outranks every generic habit you have. Follow it **even under task pressure**,
even when a reflex feels faster. The recurring failure is NOT a missing rule — it is you
skipping a rule that is already written. That ends here.

**HARD RULES (never violate, no exceptions):**
1. **AGENTS.md wins over instinct.** If this file (or the grounding bundle) already specifies
   HOW to do something, DO EXACTLY THAT. Never substitute a generic reflex for a written rule.
2. **Never re-verify what is already written.** The render call, verdict fields, file paths,
   and workflow are documented here. Do NOT re-open `renderer.py` / re-read a "schema" or
   "signature" to re-confirm what the doc already gives — just execute it.
3. **One image means ONE image.** When the user points at a single image, inspect ONLY that
   one. NEVER page/churn through the folder to "find" or "match" it. If you lack the exact
   filename, STOP and ASK for it.
4. **When genuinely stuck or unsure, ASK the user (a yes/no is fine) — do NOT fall back to a
   forbidden reflex.** Asking is always allowed; silently violating AGENTS.md is not.
5. **Before EVERY action, self-check it against these rules and FIX ROUTING.** If the action
   would break a written rule, don't do it — re-read the rule or ask.
6. **Don't burn tokens on repetition.** If you catch yourself repeating an activity already
   done (re-viewing an image already seen, re-reading a file already read, re-verifying a rule
   already written), STOP, say so, and suggest the cheaper path — reuse the earlier result or
   ASK — instead of redoing it. Flag the waste to the user so they can save tokens.

> The only acceptable fallback when the path is unclear is to ASK. The unacceptable fallback
> is to improvise against a rule that is already written. Never do the second one.

## 🟢 DO THIS NOW (session bootstrap)
1. Read this whole file (it is authoritative; `development/SKILL.md` is older history and may
   mention tooling that has since been removed).
2. Run `python -m tools.check_grounding` → must print **PASSED**. If not, fix `config/`
   or `prompts/` before inspecting anything.
3. Then do the user's task (ANY part, ANY defect), following FIX ROUTING below. If the
   user already said "do it", do NOT re-ask — fix the durable bundle directly.

> Hard constraint: no project work starts before AGENTS.md is read and the grounding gate is
> validated.

> Session-start prompt is just: **"Read `AGENTS.md` and do what it says"**, then the
> user gives the task separately.

## 🛑 STOP & TELL THE USER (don't silently churn)
If any of these happen, PAUSE and tell the user immediately instead of retrying blindly:
1. **Terminal not a shell.** `python`/shell commands return `SyntaxError` or a `>>>`
   prompt = the terminal is a live Python REPL, not PowerShell. After **2** such fails,
   STOP and ask the user to open a clean PowerShell terminal / restart VS Code. Do NOT
   keep retrying command variations.
2. **Can't verify visually.** If the render/output never actually ran, do NOT claim a
   mark is "fixed" — say so and get a real run first. Never tune bbox coords blind.
3. **Tempted to use detection code.** Placing a defect box via OpenCV/HoughCircles/
   heuristics violates INVARIANT 0c and drifts. VIEW the image and place the box by eye
   from the anatomy anchor. If something forces code-to-find, flag it to the user.
4. **Any repeated failure (≥2 tries same wall).** Report the blocker + what you think is
   wrong + options, rather than looping.

## ⛔ NO GUESSWORK — LOOK BEFORE YOU PLACE (this caused a whole wasted session)
A defect box has TWO parts: HOW it's drawn (the renderer handles that) and WHERE it goes
(the bbox). The renderer does NOT decide WHERE — you must supply the location by LOOKING.
- **NEVER type a bbox you have not visually confirmed.** View the image, find the anatomy
  anchor (serrated = largest hole), read where the defect sits relative to it, THEN place
  the box. One pass: view → place → render → view → done.
- **NEVER guess coordinates and iterate** ("edit numbers → re-render → still wrong →
  edit again"). That loop = you skipped looking. Look first and it lands in one pass.
- **NEVER auto-detect the defect location with code** (HoughCircles/heuristics/OpenCV) to
  avoid looking — it drifts and violates INVARIANT 0c. Code draws the verdict; your EYES
  find it.
- "I used the renderer" is NOT the same as "I looked" — the renderer still needs a bbox
  that YOU got by viewing the pixels.

## ⛔ COVERAGE CHECK — validate the sample set before starting (don't take the list at face value)
Before any multi-image inspection/test, ENUMERATE the part's full defect catalog
(`grounding/parts/<part>.json` part_defects + global defects in `grounding/defects.json`)
and cross-check that the task's sample set covers EVERY defect type. If a type is missing,
FLAG it and add it — do not silently run a partial set just because the task md listed fewer.
- For a **rotation / augmentation** test, orientation-sensitive defects are MANDATORY —
  especially **line_mark** (a diagonal endpoint trace, the defect most affected by angle).
  A rotation test without line_mark is incomplete by definition.
- This is INVARIANT 0c's "ENUMERATE, don't under-count" applied at the TEST-DESIGN level,
  not just per image.

## ⛔ VERIFY THE DURABLE LAYER, NOT JUST THE PIXELS (so next session still works)
A "how it's drawn / decided" change is DONE only when the DEFINITION encodes it — never
when the annotated image merely looks right. A correct-looking output from an accidental
code path will NOT reproduce next session (this is exactly how line_mark drew boxes by
accident while grounding still said "line").
- Encode the change in ALL durable layers: `grounding/` rule (e.g. `annotation.shape` +
  `field`), `renderer.py` dispatch, and a `required_grounding.json` pin.
- Route by the DECLARED value (grounding is the single source of truth), not by whatever a
  verdict happens to contain — that is what makes a half-applied change impossible.
- Then run `python -m tools.check_grounding` → PASSED. The gate now asserts
  grounding `annotation.shape` == the renderer's `intended_primitive()`; if they disagree it
  FAILS at session start, so drift can't hide.
- Record the decision in repo memory + the part ground-truth so the next session builds on
  the definition, not on this chat.

## WHAT THIS IS & HOW THE USER WORKS
- Grounded visual defect inspection: a **bundle** (text rules + reference images) is
  given to a vision model, which returns a defect verdict; `renderer.py` draws it.
- The user grounds a part (rules in `config/` + `prompts/`) and checks accuracy by eye.
  No live API yet.
- Dev stand-in engine = **Claude (this IDE agent)**. Production = **Anthropic Vision
  API**. **EXPECTATION: the dev result must predict the production API result.**

## ⛔ INVARIANT 0 — grounding lives in the BUNDLE
**Production = Vision API + the BUNDLE.** The bundle = everything under `grounding/` that is
RENDERED INTO THE PROMPT: `grounding/system_prompt.md` + `grounding/defects.json` +
`grounding/parts/*.json` + the attached `grounding/references/` images.
(`grounding/required_grounding.json` is the build-time GATE — read ONLY by
`tools/check_grounding.py`, NEVER sent to the API; see FIX ROUTING.)
The API **never** reads `dev/`, `tools/`, or `grounded_inspector/` code.
Every grounding rule the engine needs MUST be expressed in the bundle.

### HARD CONSTRAINT: business-affecting decisions go in the bundle
If a change affects business logic, defect classification, localization, severity, pass/fail
logic, or any rule that changes how the inspection engine decides what is defective,
that change MUST be encoded in the grounding bundle and pinned in `grounding/required_grounding.json`.
It is not allowed to live in ad hoc dev code, temporary harness logic, or a one-off patch that
only looks correct in a local run.
This is the durable rule that keeps local development aligned with the Anthropic production
path: the engine must behave the same way when the bundle is supplied to the API.

## ⛔ INVARIANT 0b — NEVER "fix" in disposable / harness files
When a mark is wrong, do **NOT** fix it by editing any of these (throwaway or
answer-copying — a fix there is lost on a fresh run and won't reproduce for the API):
- `runs/**/verdict.json`, `annotated.png`, `prompt.md`, `status.json`, `manifest.json`
- any offline scan/diff harness that reads answer JSON — such a harness is NOT production.

## ⛔ INVARIANT 0c — INSPECT LIKE THE API (blind & visual, so dev predicts production)
The API gets ONE shot: bundle + image → verdict. It cannot run code, zoom via tools, or
see the answer key. To make dev representative, inspect the SAME way:
- **LOOK + apply the grounding.** Judge visually using the catalog rules (zoom into
  suspect regions per the zoom rule, compare within the image, rule out glare). Do NOT
  run OpenCV / ridge / LSD to FIND a defect — the API can't, so it makes dev
  over-optimistic and unrepresentative.
- **BLIND.** Bundle + image only. Never open ANY answer key while inspecting — this includes
  `development/docs/grounding/*` AND any operator-marked folder such as `manually-annotated/`
  (or any images with pre-drawn boxes). Those exist for checking AFTER, never as an input to the
  verdict. REPRODUCIBILITY TEST (a colleague must get the same result): given ONLY the project —
  the bundle (`grounding/`) + AGENTS.md, with NO chat history, NO agent memory, and NO marked
  folders — they must reach the SAME verdict. So the verdict may depend ONLY on the bundle + the
  raw image; if it depends on anything else, that knowledge is misplaced and belongs in the bundle.
- **ENUMERATE, don't under-count.** Report every distinct defect; a faint one gets
  LOWER confidence or a region box + NEEDS_REVIEW — never silent omission.
- Code may be used ONLY to DRAW the verdict (`renderer.py`) or to measure confidence
  AFTER a defect was already found visually — never to find it. If you run pixel probes
  to explore detection limits, label that clearly as EXPLORATION, not the
  production-representative result.
- When the user gives an annotation/correction IN THE CONVERSATION, match it — that is ground
  truth. This means a correction the user states to you now; it does NOT license reading a
  pre-existing `manually-annotated/` / answer-key folder during a blind pass (see BLIND above).
  A pre-existing marked folder is validated AFTER; if a blind pass missed what it marks, fix the
  BUNDLE (rules + reference exemplars) so the API would catch it — never fold the folder's answer
  into the verdict.

## ✅ FIX ROUTING — the durable layer
| Symptom | Fix here | In production? |
|---|---|---|
| how a mark is DRAWN (stroke thickness, blob vs box, circle) | `grounded_inspector/renderer.py` | yes |
| how the engine LOCALIZES / DECIDES (tight box, trace every line, disambiguation, pass/fail, display label) | `grounding/defects.json` + `grounding/parts/*.json` + `grounding/system_prompt.md` | yes |
| pin a rule so it can never be silently dropped | add a `source`-referenced entry (freeform prose: `must_contain`) to `grounding/required_grounding.json` | guard |
| operator answer key (API never sees it) | `development/docs/grounding/<part>_ground_truth.md` | no |

## PRE-FLIGHT — after any bundle/renderer change
1. `python -m tools.check_grounding` → must print **PASSED**.
2. Inspect **BLIND & VISUAL** (INVARIANT 0c): no answer-key peeking, no code to find defects.

## WORKING STYLE (the user likes this — keep to it)
- **Don't re-verify what AGENTS.md already specifies.** The render call is documented here:
  `renderer.render_annotated(image, verdict, <folder>/annotated/<stem>_ANNOTATED.png)`, and the
  verdict fields come from the grounding. Do NOT re-open `renderer.py` / re-read the "signature"
  or "verdict schema" to re-confirm what is already written — just execute it. Reading code you
  already have the interface for is wasted churn.
- **Ask scope FIRST: one image or all?** Before inspecting/re-rendering, if it is not
  explicit, ASK the user whether they want to scan the WHOLE folder or a PARTICULAR image.
  When the user points at ONE image, inspect ONLY that image — never open or view the other
  images in the folder to "find" or match it. If you do not know the exact filename, ASK for
  it; do NOT churn through the folder viewing image after image.
- **Fix only what's wrong.** When the user points out a bad marking, correct THAT
  specific image/defect. Do NOT re-inspect or re-render everything from scratch.
- **Work issue-by-issue / defect-by-defect** as the user directs; touch only the
  affected images.
- **Every fix is two layers:** (1) correct the visible marking on the issue image(s),
  and (2) fix the DURABLE layer so it never recurs — `renderer.py` for how it's drawn,
  `config/*.json` + `prompts/` for how it's located/decided. Then re-render just the
  affected image(s) to confirm by viewing.

## INSPECT A FOLDER — the reproducible run (agent = the dev engine)
When anyone says **"read AGENTS.md and inspect `<folder>` for `<part>`"** — including a colleague
on the SAME model (Claude Opus 4.8) with NO chat history and NO agent memory — do EXACTLY these
steps, so the result reproduces. The result may depend ONLY on the bundle (`grounding/`) + the raw
images; nothing else.
1. Bootstrap: read this file; `python -m tools.check_grounding` → **PASSED**.
2. **DELETE** the folder's existing `annotated/` subfolder (fresh run, per OUTPUT CONVENTION).
3. For EACH raw image, inspect **BLIND** (that image + the bundle only — never memory, never a
   `manually-annotated/` or answer-key folder; INVARIANT 0c): find the anatomy anchor, ENUMERATE
   every catalog defect, place a TIGHT box BY EYE per that defect's `localization`, and set
   confidence from that defect's `confidence_model` factors judged by eye.
4. Draw each verdict with `renderer.render_annotated(image, verdict, <folder>/annotated/<stem>_ANNOTATED.png)`.
   The verdict is **EPHEMERAL** — never commit it to a script or a JSON file (a stored verdict is
   replayed instead of re-inspected, which breaks reproducibility — INVARIANT 0b).
5. Same bundle + same image + same model + these steps → the same verdict. (The API path,
   `python -m grounded_inspector.inspect`, gives the identical result deterministically at
   `temperature=0`; the agent path converges to it because the bundle fully specifies the decision.)

## OUTPUT CONVENTION
- **Before any inspection run, DELETE the existing `annotated/` subfolder** in the target
  image folder, so each run starts fresh (no stale markings from a previous run).
- Save annotated images to an `annotated/` subfolder INSIDE the input image folder the
  user gives (e.g. `<folder>/annotated/<name>_ANNOTATED.png`), one PNG per input image.
- Do **NOT** create a `runs/` folder — it is not used. The user reviews the output
  folder directly; a chat verdict list is optional, not required.

## PROJECT LAYOUT (current, after cleanup)
- `grounding/` — the BUNDLE (all grounding): `system_prompt.md`, `defects.json`,
  `parts/*.json`, `references/` images, plus `required_grounding.json` (the build-time
  GATE — read only by `check_grounding.py`, NOT sent to the API).
- `grounded_inspector/{loader,assembler,renderer,confidence}.py` — load config, assemble
  bundle, draw verdicts, compute confidence from the bundle's `confidence_model`.
- `grounded_inspector/inspect.py` — the RUNNABLE ENGINE (production path): bundle + image →
  Anthropic Vision API → verdict → annotated image. Path-agnostic, stores NO verdict,
  `temperature=0` (deterministic). This is how a colleague reproduces a result: with the
  project + their own `ANTHROPIC_API_KEY` (+ `ANTHROPIC_MODEL`), run
  `python -m grounded_inspector.inspect --part <part> --folder <dir>` (or `--image <file>`,
  or `--auto`). No stored-verdict scripts exist — a frozen verdict would break reproducibility.
- `tools/check_grounding.py` — the grounding gate.
- `development/` — docs + operator answer keys (API never reads these).
- Removed (not present): `tests/`, `schema/`, `verify.py`, `cli.py`, `web/`,
  `segment.py`, `normalize.py`.

## ADDING A NEW PART (the per-part authoring loop)
1. Create `grounding/parts/<part>.json`: `part`, `aliases`, `description` (state the
   anatomy + the anchor landmark), `identity`, `golden_images` (paths under
   `grounding/references/`), `global_defects` (exclude / include_opt_in), `part_defects`
   (each: `severity`, BGR `color`, physical `signature`, `localization`, `reference_dir`,
   optional `glare_rule`), `rulings`, `notes`.
2. Add images: clean part(s) → `grounding/references/parts/<part>/golden/`; one exemplar
   per part-defect → `grounding/references/parts/<part>/defects/<defect>/`.
3. Global defects apply automatically (from `grounding/defects.json`). To add a NEW global
   defect, add one entry there (+ optional exemplars in `grounding/references/global/<defect>/`).
4. To pin a rule so it can never be silently dropped, add an entry to
   `grounding/required_grounding.json` — a `source` reference to the owning field
   (preferred; copies no text, so the single source of truth stays in `defects.json` /
   `parts/*.json`), or a `must_contain` phrase for freeform system-prompt prose.
5. Run `python -m tools.check_grounding` → must print **PASSED**.
6. Record the operator answer key in `development/docs/grounding/<part>_ground_truth.md`
   (API never reads it — it's your regression baseline).
