# GroundedInspector Modular Inspection Architecture

## Runtime

Explicit-part inspection now follows:

```
image
  -> shared anatomy
  -> independent defect inspectors
  -> deterministic verdict aggregator
  -> renderer
```

## Responsibilities

### Shared anatomy
Establish physical facts once, such as:
- face/orientation
- hole identity
- inspection zones
- other part-specific prerequisites

### Independent defect inspectors
Each configured defect is evaluated in its own model request using:
- the input image
- shared anatomy facts
- its own authored decision
- its own visual exemplars

An inspector must not classify or suppress unrelated defects.

### Aggregator
The aggregator is deterministic. It:
- combines independent defect results
- creates checkpoints
- resolves primary defect
- preserves the external verdict contract
- makes NEEDS_REVIEW win when a required checkpoint is unresolved

### Renderer
The renderer displays the verdict. It may perform safety operations such as
coordinate validation and part-boundary clipping, but it must not semantically
reclassify or suppress defects.

## Migration boundary

The inspection runtime has been migrated to the modular architecture.

Explicit-part mode runs shared anatomy followed by every configured defect inspector.
Auto-identification uses a separate part-identification stage, then routes each
identified instance through the same shared-anatomy, independent-defect, aggregation,
and rendering stages.

## Stability principle

The architecture is designed around:

> Shared facts, independent decisions.

The purpose is to make a change to one defect less capable of silently changing an
unrelated defect decision. Regression testing remains required before considering
the migration production-stable.


## Validation

Local validation is the current acceptance step. Run the application against the
approved bracket image folder and inspect the generated annotated output in one shot.
Automated regression protection can be added later after the visual results are accepted.
