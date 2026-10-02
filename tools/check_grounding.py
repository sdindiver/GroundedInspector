"""Self-check: verify the grounding bundle is FULLY SELF-CONTAINED.

WHY THIS EXISTS
---------------
The engine that produces verdicts is swappable: today it is Claude-in-the-IDE,
tomorrow it is the Anthropic API. The API only ever sees what we put into the
BUNDLE (prompts/system_prompt.md + the rendered prompt from config + attached
images + schema/verdict.schema.json). It does NOT read SKILL.md, README.md, or
docs/grounding/*.md - those are operator notes only.

Therefore EVERY piece of grounding knowledge (defect signatures, disambiguation
tests, glare rules, annotation/line-drawing rules, rulings, notes, part identity)
MUST appear in the rendered prompt. If a rule lives only in an agent-facing doc,
the API will silently diverge. This script fails (exit 1) if anything grounding-
relevant does not reach the prompt, for both single-part and auto modes.

RUN THIS at the start of a session and after ANY change to config/, prompts/,
grounded_inspector/config.py or grounding.py:

    python -m tools.check_grounding
"""
from __future__ import annotations

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from grounded_inspector import loader as C  # noqa: E402
from grounded_inspector import assembler as G  # noqa: E402


def _sample_image() -> str:
    imgs = glob.glob(os.path.join(HERE, "runs", "jobs", "**", "input.*"), recursive=True)
    if imgs:
        return imgs[0]
    refs = glob.glob(os.path.join(HERE, "grounding", "references", "**", "*.jpg"), recursive=True)
    return refs[0] if refs else os.path.join(HERE, "runs", "_none.jpg")


def _check_text_present(prompt, needles, ctx, failures):
    for label, text in needles:
        if not text or not str(text).strip():
            continue
        probe = str(text).strip()[:60]  # first 60 chars proves it was rendered
        if probe not in prompt:
            failures.append(f"[{ctx}] missing from prompt: {label} -> \"{probe[:50]}...\"")


def _defect_needles(d, prefix):
    needles = [(f"{prefix}{d['category']}.signature", d.get("signature"))]
    ann = d.get("annotation") or {}
    if ann.get("instruction"):
        needles.append((f"{prefix}{d['category']}.annotation", ann["instruction"]))
    for k, v in (d.get("guidance") or {}).items():
        val = G._prose(v)
        needles.append((f"{prefix}{d['category']}.{k}", val))
    return needles


def check_part(part_name, failures):
    cfg = C.load_part(part_name)
    catalog = C.load_global_catalog()
    defects = C.resolve_defects(cfg, catalog)
    prompt = G.render_prompt(G.build_bundle(part_name, _sample_image()))

    needles = []
    for d in defects:
        needles += _defect_needles(d, "")
    for r in C.resolve_ref_list(cfg.get("rulings", [])):
        needles.append(("ruling", G._prose(r)))
    idn = cfg.get("identity") or {}
    if idn.get("summary"):
        needles.append(("identity.summary", idn["summary"]))
    _check_text_present(prompt, needles, f"single:{part_name}", failures)


def check_auto(failures):
    prompt = G.render_auto_prompt(G.build_auto_bundle(_sample_image()))
    catalog = C.load_global_catalog()
    for cfg in C.list_parts():
        pname = cfg.get("part")
        for d in C.resolve_defects(cfg, catalog):
            _check_text_present(prompt, _defect_needles(d, f"{pname}/"), "auto", failures)
        idn = cfg.get("identity") or {}
        if idn.get("summary"):
            _check_text_present(prompt, [("identity.summary", idn["summary"])], "auto", failures)
        needles = [(f"{pname}/ruling", G._prose(r)) for r in C.resolve_ref_list(cfg.get("rulings", []))]
        needles += [(f"{pname}/note", G._prose(n)) for n in C.resolve_ref_list(cfg.get("notes", []))]
        _check_text_present(prompt, needles, "auto", failures)


def check_line_defects_have_annotation(failures):
    """A defect described as a line/scratch MUST declare an annotation (shape 'box' or
    'line') with a matching field, so the engine emits geometry the renderer can draw."""
    catalog = C.load_global_catalog()
    for cat, spec in catalog.get("defects", {}).items():
        sig = (spec.get("signature") or "").lower()
        looks_linear = "line" in cat.lower() or "linear trace" in sig or "scratch" in cat.lower()
        shape = (spec.get("annotation") or {}).get("shape")
        if looks_linear and shape not in ("box", "line"):
            failures.append(f"[config] global defect '{cat}' looks line-shaped but declares no "
                            f"annotation.shape ('box' or 'line') - the renderer can't draw it.")


def check_annotation_render_consistency(failures):
    """Every defect that declares an annotation must declare a shape the renderer supports,
    a field that matches that shape, AND the primitive the renderer will actually draw must
    equal the declared shape. This is the backstop against a half-applied 'how it's drawn'
    change - grounding saying one shape while the renderer draws another (the exact line_mark
    box-vs-trace drift). Keyed on the renderer's own intended_primitive() so the two layers
    can never silently disagree."""
    from grounded_inspector import renderer as R
    valid_fields = {"line": {"lines", "line"}, "box": {"bbox"}, "circle": {"bbox"}}

    def _check(cat, spec):
        ann = spec.get("annotation") or {}
        if not ann:
            return
        shape = ann.get("shape")
        field = ann.get("field")
        if shape not in R.SUPPORTED_ANNOTATION_SHAPES:
            failures.append(f"[config] defect '{cat}' annotation.shape='{shape}' is not a renderer-"
                            f"supported shape {sorted(R.SUPPORTED_ANNOTATION_SHAPES)}.")
            return
        if field is not None and field not in valid_fields[shape]:
            failures.append(f"[config] defect '{cat}' annotation.field='{field}' does not match "
                            f"shape '{shape}' (expected one of {sorted(valid_fields[shape])}).")
        drawn = R.intended_primitive(cat)
        if drawn != shape:
            failures.append(f"[config] defect '{cat}' declares annotation.shape='{shape}' but the "
                            f"renderer will draw '{drawn}' - grounding and renderer disagree "
                            f"(half-applied drawing change).")

    for name, spec in C.load_global_catalog().get("defects", {}).items():
        _check(name, spec)
    for part in C.list_parts():
        for name, spec in (part.get("part_defects", {}) or {}).items():
            _check(name, spec)


# QMS-exact display labels. The renderer resolves a verdict's `category` to these via
# config (display_name); if a name is dropped from config the annotated label silently
# regresses to a title-cased guess (e.g. 'Dark Spot' instead of QMS's 'Dark Spots',
# or 'Incomplete Embossing' instead of 'Incomplete/Shallow Embossing'). Pin them here
# so a fresh bundled/API run always renders the same labels QMS uses.
REQUIRED_DISPLAY_NAMES = {
    "line_mark": "Line Mark",
    "dark_spot": "Dark Spots",
    "dark_mark": "Dark Marks",
    "white_mark": "White Mark",
    "serration_missing": "Serration Missing",
    "incomplete_embossing": "Incomplete/Shallow Embossing",
    "embossing_missing": "Embossing Missing",
}


def check_display_names(failures):
    """Fail if any QMS-exact display name is missing/changed in the config bundle."""
    names = {}
    cat = C.load_global_catalog()
    for name, spec in cat.get("defects", {}).items():
        if spec.get("display_name"):
            names[name.lower()] = spec["display_name"]
    for cfg in C.list_parts():
        for name, spec in (cfg.get("part_defects", {}) or {}).items():
            if spec.get("display_name"):
                names[name.lower()] = spec["display_name"]
    for cat_key, expected in REQUIRED_DISPLAY_NAMES.items():
        got = names.get(cat_key)
        if got != expected:
            failures.append(
                f"[display_name] '{cat_key}' must declare display_name "
                f"\"{expected}\" in config (got {got!r}). Add/restore it so the "
                f"annotated label matches QMS in a fresh bundled run.")


def _all_rendered_prompts() -> str:
    """Concatenate every rendered prompt (each single-part prompt + the auto
    prompt) so a required-grounding pin can be found wherever it is meant to appear."""
    img = _sample_image()
    chunks = [G.render_auto_prompt(G.build_auto_bundle(img))]
    for cfg in C.list_parts():
        chunks.append(G.render_prompt(G.build_bundle(cfg.get("part"), img)))
    return "\n\n".join(chunks)


def _resolve_required_source(source):
    """Resolve a REFERENCE-BASED pin to (text, err).

    `text` is the config field the pin points at (the single source of truth in
    defects.json / parts/*.json); `err` is a human message when it cannot be
    resolved (missing part, missing/empty field = the concept was deleted). This
    is what lets a pin guard a concept WITHOUT copying its rule text, so the gate
    can never drift out of sync with a reworded phrase.

    source shape:
      {"defect": "line_mark", "field": "zoom_rule"}                 global defect field
      {"part": "bracket", "defect": "serration_missing", "field": "glare_rule"}  part defect field
      {"defect": "line_mark", "field": "annotation.instruction"}    dotted path into the field
    """
    field = source.get("field")
    defect = source.get("defect")
    if not field:
        return None, f"source {source} has no 'field'"
    if not defect:
        return None, f"source {source} has no 'defect'"
    part = source.get("part")
    try:
        if part:
            spec = (C.load_part(part).get("part_defects") or {}).get(defect)
            where = f"part '{part}' defect '{defect}'"
        else:
            spec = C.load_global_catalog().get("defects", {}).get(defect)
            where = f"global defect '{defect}'"
    except KeyError:
        return None, f"part '{part}' does not exist in config"
    if not spec:
        return None, f"{where} does not exist in config"
    node = spec
    for key in field.split("."):
        if not isinstance(node, dict):
            return None, f"{where} field path '{field}' is invalid"
        node = node.get(key)
    if isinstance(node, (list, tuple)):
        node = G._prose(node)
    if not node or not str(node).strip():
        return None, f"{where} field '{field}' is missing or empty"
    return str(node), None


def check_required_grounding(failures):
    """Fail if any concept DECLARED REQUIRED in grounding/required_grounding.json is
    absent from the rendered bundle. This catches what the forward config->prompt
    check cannot: a required concept deleted from config entirely, or only ever
    written into an agent-only doc (SKILL.md). The API only sees the bundle, so a
    missing required concept means it would silently diverge.

    Two kinds of pin:
      - REFERENCE-BASED ("source"): points at the config field that owns the rule.
        The gate asserts the field EXISTS (catches deletion) and its text REACHES
        the rendered bundle. No rule text is copied, so the single source of truth
        stays in defects.json / parts/*.json.
      - LITERAL ("must_contain"): a phrase, used ONLY for grounding that lives in
        freeform prose with no field path (system_prompt.md universals, part
        rulings/notes)."""
    path = os.path.join(HERE, "grounding", "required_grounding.json")
    if not os.path.isfile(path):
        failures.append("[grounding-gate] grounding/required_grounding.json is missing - the "
                        "required-grounding guardrail is gone. Restore it.")
        return
    spec = json.load(open(path, encoding="utf-8"))
    bundle = _all_rendered_prompts()
    for entry in spec.get("required", []):
        eid = entry.get("id", "?")
        source = entry.get("source")
        if source:
            text, err = _resolve_required_source(source)
            if err:
                failures.append(f"[grounding-gate] required grounding '{eid}' cannot be resolved: "
                                f"{err}. The concept was deleted from config - restore it in "
                                f"defects.json / parts/*.json so the API receives it.")
                continue
            probe = text.strip()[:60]
            if probe not in bundle:
                failures.append(f"[grounding-gate] required grounding '{eid}' (source {source}) "
                                f"does not reach the rendered bundle: \"{probe[:50]}...\".")
        else:
            for phrase in entry.get("must_contain", []):
                if phrase and phrase not in bundle:
                    failures.append(f"[grounding-gate] required grounding '{eid}' missing from the "
                                    f"rendered bundle: \"{phrase[:60]}...\". It lives in freeform "
                                    f"prose (system_prompt.md / part rulings-notes); add it there.")


# The behavioral hard-rules that MUST survive verbatim in AGENTS.md. These are not about
# the bundle the API sees - they are about HOW this agent works (the reflexes the user keeps
# having to correct). Chaining them to the mandatory session gate makes them un-deletable and
# surfaced every run, from the authoritative file, not from deletable agent memory.
REQUIRED_AGENTS_DISCIPLINE = [
    "STRICT DISCIPLINE — AGENTS.md OVERRIDES YOUR REFLEXES",
    "Never re-verify what is already written",
    "One image means ONE image",
    "When genuinely stuck or unsure, ASK the user",
    "Before EVERY action, self-check it against these rules",
    "Don't burn tokens on repetition",
]


def check_agents_discipline(failures):
    """Assert the STRICT DISCIPLINE block is present verbatim in AGENTS.md. The recurring
    failure is not a missing bundle rule but the agent skipping a BEHAVIORAL rule already
    written (churning a folder, re-reading a schema). This gate makes that block impossible
    to delete or weaken: if any hard rule is gone, the session gate FAILS and no work starts."""
    path = os.path.join(HERE, "AGENTS.md")
    if not os.path.isfile(path):
        failures.append("[discipline] AGENTS.md is missing - the authoritative agent policy is "
                        "gone. Restore it before any work.")
        return
    text = open(path, encoding="utf-8").read()
    for phrase in REQUIRED_AGENTS_DISCIPLINE:
        if phrase not in text:
            failures.append(f"[discipline] AGENTS.md no longer contains the hard rule "
                            f"\"{phrase}\". The STRICT DISCIPLINE block was deleted or weakened - "
                            f"restore it at the TOP of AGENTS.md so it binds every session.")


def exemplar_crop_warnings():
    """Non-fatal: list defect exemplars that have a FULL image but no localization CROP,
    so the 'every defect exemplar = full image + tight crop' policy stays visible. This
    does NOT fail the gate - a subtle defect may be too faint to crop without misleading."""
    warns = set()
    catalog = C.load_global_catalog()
    for cfg in C.list_parts():
        for d in C.resolve_defects(cfg, catalog):
            for pair in C.pair_exemplars(d.get("reference_images", [])):
                if pair["full"] and not pair["crop"]:
                    warns.add(f"{d['category']}: {os.path.basename(pair['full'])}")
    return sorted(warns)


def main() -> int:
    failures = []
    parts = C.list_parts()
    if not parts:
        print("No parts configured.")
        return 1
    for cfg in parts:
        check_part(cfg.get("part"), failures)
    check_auto(failures)
    check_line_defects_have_annotation(failures)
    check_annotation_render_consistency(failures)
    check_display_names(failures)
    check_required_grounding(failures)
    check_agents_discipline(failures)

    if failures:
        print("GROUNDING SELF-CHECK FAILED - the bundle is NOT self-contained:\n")
        for f in failures:
            print("  x " + f)
        print("\nFix: put the missing grounding in config/*.json (as a defect field, ruling, "
              "identity, or annotation) and make grounding.py render it. Never rely on SKILL.md "
              "or docs/ for anything the engine needs - the API does not read them.")
        return 1

    print(f"GROUNDING SELF-CHECK PASSED: every grounding field for {len(parts)} part(s) "
          f"reaches BOTH the single-part and auto prompts; required-grounding gate "
          f"satisfied; QMS display names present in config; line defects declare a box/line "
          f"annotation; grounding<->renderer draw shapes agree. Bundle is self-contained.")
    crop_warns = exemplar_crop_warnings()
    if crop_warns:
        print(f"\nNOTE (non-fatal) - {len(crop_warns)} defect exemplar(s) have a full image but "
              f"no localization CROP (policy: every exemplar = full image + tight crop, so the API "
              f"is shown WHERE the defect is). Add one with tools/make_exemplar_crop, or leave it "
              f"if the defect is too faint to crop without misleading:")
        for w in crop_warns:
            print("  - " + w)
    # Printed every session (bootstrap runs this gate) so the working agreement survives
    # a memory wipe - it lives in code, not in deletable memory.
    print(
        "\nSTRICT DISCIPLINE (AGENTS.md OVERRIDES YOUR REFLEXES, ALWAYS - obey even under pressure):\n"
        "  1. AGENTS.md wins over instinct. If it already specifies HOW, do EXACTLY that.\n"
        "  2. Never re-verify what is already written (render call, schema, paths, workflow).\n"
        "  3. One image means ONE image - never churn the folder; if unsure of the file, ASK.\n"
        "  4. When genuinely stuck or unsure, ASK the user (yes/no is fine) - never fall back\n"
        "     to a forbidden reflex. Asking is allowed; silently violating AGENTS.md is not.\n"
        "  5. Before EVERY action, self-check it against these rules and FIX ROUTING.\n"
        "  6. Don't burn tokens on repetition - if you catch yourself redoing a done activity\n"
        "     (re-viewing an image, re-reading a file, re-verifying a written rule), STOP, say\n"
        "     so, and suggest the cheaper path (reuse the earlier result or ASK).\n"
        "\nWORKING AGREEMENT (AGENTS.md is authoritative; obey it, don't just read it):\n"
        "  1. The rule IS the instruction. If AGENTS.md or the grounding bundle already\n"
        "     specifies it, EXECUTE it - do NOT re-ask or offer it back as an option.\n"
        "  2. Localize BY EYE from the anatomy anchor, per each defect's annotation/\n"
        "     localization in grounding/. Never detection code, never blind coord guessing.\n"
        "  3. One pass: VIEW -> place -> render -> VIEW to confirm. A result is 'done' only\n"
        "     after it is verified by a view or this gate - never on assertion alone."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
