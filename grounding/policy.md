# Universal inspection policy

These rules apply to every inspection stage.

## Evidence

- Use visible evidence only.
- Do not treat glare, reflection, normal finish, shadows, or explicit IGNORE evidence as defect evidence.
- Do not turn an uncertain observation into a defect.
- When a rule says REVIEW, do not guess.
- Count every distinct actionable instance.
- Localize reported defects tightly to the actual defective feature.
- When a defect has attached exemplar images, use them as visual grounding examples for that defect's appearance and boundary. Compare the feature itself, not exact position, size, lighting, or orientation. Exemplars support the written decision; they do not override it.

## Architecture

- Shared anatomy facts are established once before dependent defect checks.
- Each defect decision is independent.
- A defect inspector must not classify, suppress, or reinterpret unrelated defects.
- Deterministic validation and aggregation belong in code.
- The renderer displays verdicts and must not semantically reclassify defects.

## Inspection completeness

- Run every configured inspection item.
- Every inspection item has exactly one state: DEFECT, CLEAR, or NEEDS_REVIEW.
- An unresolved required checkpoint makes the overall result NEEDS_REVIEW.
- Report only categories in the resolved defect catalog.
