# Grounded inspection output contract

The universal inspection policy is loaded from `grounding/policy.md`.

This file defines the legacy single-pass output contract used by compatibility
(auto-identification) mode. The modular explicit-part pipeline uses stage-specific
JSON contracts and the same universal policy.

For legacy single-part inspection, respond with ONE JSON object ONLY (no prose, no
markdown fences):

{
  "part": "<part name>",
  "image": "<input image basename>",
  "result": "OK | DEFECT | NEEDS_REVIEW",
  "primary": "<category or null>",
  "needs_review_reason": "<string or null>",
  "checkpoints": [
    {
      "check": "<inspection item or prerequisite>",
      "result": "CLEARED | DEFECT | NEEDS_REVIEW",
      "evidence": "<what you actually saw at the required location>"
    }
  ],
  "defects": [
    {
      "category": "<catalog category>",
      "scope": "global | part",
      "severity": <0-5>,
      "bbox": [x, y, w, h],
      "line": [x1, y1, x2, y2],
      "lines": [[x1, y1, x2, y2], ...],
      "location": "<clock-position / plain-language spot>",
      "confidence": <0-1>,
      "reason": "<one sentence why>"
    }
  ]
}

Use only the geometry fields needed by the defect. Coordinates are normalized 0..1 in
display orientation.
