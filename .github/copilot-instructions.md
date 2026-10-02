# GroundedInspector Copilot Instructions

This repository is GroundedInspector.

## Project default
- Read AGENTS.md at the workspace root before starting any project work.
- Follow AGENTS.md as the authoritative repo policy for this project.
- Treat the grounding bundle as the single source of truth for defect logic and production behavior.
- Keep business-affecting decisions in the grounding bundle, not in ad hoc code or disposable outputs.
- Run `python -m tools.check_grounding` after bundle or renderer changes and confirm it prints PASSED.

## Project direction
- Stay grounded in visual inspection for manufactured metal parts.
- Keep the system aligned with the bundle-first architecture and Anthropic production path.
- Fix by layer: grounding bundle, renderer, deterministic logic, evaluation.
- Prefer evidence-first, one-pass localization, and durable reproducible fixes.
