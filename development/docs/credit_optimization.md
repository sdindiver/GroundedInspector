# Credit & Token Optimization — Grounded Inspection Sessions

Why one night burned ~20,000 Copilot credits, and how to avoid it. Based on the
2026-09-22 sessions (204 agent turns, 100 `view_image` calls).

## TL;DR
The cost is **not** rendering. Rendering (`renderer.py`) runs locally and is **free**.
The cost is the model **viewing** each rendered image (`view_image` = a vision call),
because every viewed image is re-sent in context on every later turn. Fewer view/adjust
loops = dramatically fewer tokens.

---

## What actually happened (measured from the session store)

| Session | Turns | `view_image` calls | Files touched |
|---|---|---|---|
| 66c5e5e5… (annotated/ pairing) | 154 | 65 | 131 |
| 98d27bd4… ("Try Again", overnight) | 50 | 35 | 63 |
| **Total** | **204** | **100** | **194** |

Three multipliers stacked:
1. **Claude Opus (high premium-request multiplier)** applied across 200+ turns.
2. **204 agent turns** — each turn can fire multiple premium requests.
3. **100 vision views** — the dominant sink. Each image ≈ 1,500 tokens AND persists in
   context, so it gets re-sent on every following turn (cost grows quadratically).

---

## The two steps — only ONE costs tokens

| Step | Who runs it | Cost |
|---|---|---|
| **Render / re-render** — draw the box, save PNG | Local Python (`renderer.py`) | **FREE** (0 tokens) |
| **`view_image`** — model looks at the PNG to judge it | The AI model (vision) | **EXPENSIVE** (~1,500 tokens/image, re-sent every later turn) |

The wasted credits came from the **loop**, not the rendering:

```
place box → render (free) → view_image (tokens) → wrong →
adjust → render (free) → view_image (tokens) → wrong → ... ×100
```

---

## The rules that prevent it (already in AGENTS.md)

### 1. One-pass placement — "view → place → render → view → done"
LOOK once, place the box by eye correctly the first time, render, view ONCE to confirm.
Target **2 `view_image` calls per defect**, not ten. The 100 views mean boxes were guessed
and re-corrected repeatedly — that is the whole cost.

### 2. Never guess-and-iterate coordinates
Typing a bbox you haven't visually confirmed forces a view→adjust→view loop. Look at the
anatomy anchor first; place it right once.

### 3. Verify the durable layer, not the pixels
Encode fixes in `grounding/` + `renderer.py` so the result reproduces
next session without re-viewing everything again.

---

## Optimization checklist

- [ ] **Place boxes in ONE pass.** Look → place → render → view once → done. No iterate loops.
- [ ] **Start fresh sessions often.** Both sessions grew to 150/50 turns without a reset;
      old images kept re-billing. A new session drops accumulated image context.
- [ ] **Batch views.** Render all affected images, then view them together — don't
      one-render-one-view in a long chain.
- [ ] **Only view what changed.** Fix issue-by-issue; re-view just the affected image, never
      re-inspect/re-render the whole set.
- [ ] **Use a cheaper model for non-visual work.** File edits, JSON/config, and
      `check_grounding` runs don't need Opus + vision. Reserve Opus + vision for the actual
      place-the-box visual judgment.
- [ ] **Delete stale `annotated/` before a run** (already required) so you never re-view old
      markings.

---

## Copilot credits vs Anthropic API tokens (they are different)

- **Copilot credits** = per-request accounting × Opus multiplier × 204 turns → the 20,000 figure.
- **Anthropic API** = billed by tokens. Raw volume is still large (~4–10M input tokens for
  these sessions because of 100 re-viewed images), BUT:
  - **Prompt caching** discounts the repeated stable prefix (system prompt, bundle, unchanged
    images) by ~10×. Your repeated-image loop is exactly what caching cheapens.
  - **No per-request multiplier** — the "204 turns × Opus" penalty disappears.
- Net: on the direct API the same work would likely cost **well below** the 20K-credit
  equivalent — but the #1 lever on *either* backend is the same: **cut the redundant
  `view_image` loops.**

> Exact billing lives in **GitHub → Settings → Billing → Plans and usage**, not in the local
> session store. The numbers above are inferred from stored session activity.
