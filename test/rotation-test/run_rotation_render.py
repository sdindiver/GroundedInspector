from pathlib import Path
from PIL import Image, ImageOps
import shutil
import sys

sys.path.insert(0, str(Path(r'c:\workspace-ai\GroundedInspector').resolve()))
from grounded_inspector import renderer

base = Path(r'c:\workspace-ai\images_640\bracket')
out = base / 'rotation_test'
if out.exists():
    shutil.rmtree(out)
out.mkdir(parents=True, exist_ok=True)

# Anatomy-anchored boxes for the rotated test set. These are not guessed from image
# frame coordinates: they are placed by bracket geometry (largest hole, strap edge,
# VA zone) after the part has been rotated, matching the bundle rules in
# grounding/parts/bracket.json.
manually_tuned = {
    # serration_missing: largest hole, upper-right after 143deg rotation
    'IMG20260824163907_640_rot143.png': (0.595, 0.305, 0.09, 0.09),
    # dark_spot: dark smudge on the top strap edge between the middle and right holes
    'IMG20260824164818_640_mirror.png': (0.50, 0.35, 0.13, 0.09),
    # dark_mark: near-black blotch just below-right of the serrated (left) hole
    'IMG20260824165152_640_rot68.png': (0.30, 0.44, 0.09, 0.09),
    # incomplete_embossing: VA zone between the middle hole and the left plain hole
    'IMG20260824164116_640_rot291.png': (0.38, 0.51, 0.10, 0.08),
}

jobs = [
    ('IMG20260824163907_640.png', 143, 'IMG20260824163907_640_rot143.png', 'serration_missing'),
    ('IMG20260824164818_640.png', None, 'IMG20260824164818_640_mirror.png', 'dark_spot', 'mirror'),
    ('IMG20260824165152_640.png', 68, 'IMG20260824165152_640_rot68.png', 'dark_mark'),
    ('IMG20260824164116_640.png', 291, 'IMG20260824164116_640_rot291.png', 'incomplete_embossing'),
]

for job in jobs:
    src_name, angle, out_name, defect, *rest = job
    src = base / src_name
    img = Image.open(src).convert('RGB')
    if rest and rest[0] == 'mirror':
        img = ImageOps.mirror(img)
    else:
        img = img.rotate(angle, expand=True, fillcolor=(255, 255, 255), resample=Image.Resampling.BICUBIC)

    final_path = out / out_name
    img.save(final_path)

    bbox = manually_tuned[out_name]
    verdict = {
        'result': 'DEFECT',
        'defects': [{
            'category': defect,
            'severity': 4 if defect in {'serration_missing', 'dark_spot', 'dark_mark'} else 3,
            'bbox': list(bbox),
            'display_name': {
                'serration_missing': 'Serration Missing',
                'dark_spot': 'Dark Spots',
                'dark_mark': 'Dark Mark',
                'incomplete_embossing': 'Incomplete/Shallow Embossing',
            }[defect],
        }],
    }
    ann_path = out / f'{final_path.stem}_ANNOTATED.png'
    renderer.render_annotated(str(final_path), verdict, str(ann_path))

# --- line_mark rotation set (all 5 unique samples) -------------------------------
# The groove is hand-read by eye on the UPRIGHT original (normalized x,y endpoints),
# then carried through the SAME rotation as the image so the trace stays on the
# groove. Rotating an annotation is preparation, not detection.
linemark_jobs = [
    # src, angle ('mirror' for horizontal flip), out_name, bbox (rotated-image normalized,
    # placed BY EYE tight on the visible groove & on the part), needs_review
    ('IMG20260824163734_640.png', 27, 'IMG20260824163734_640_rot27.png', (0.44, 0.48, 0.18, 0.20), True),
    ('IMG20260824163740_640.png', 118, 'IMG20260824163740_640_rot118.png', (0.42, 0.48, 0.18, 0.16), True),
    ('IMG20260824163750_640.png', 203, 'IMG20260824163750_640_rot203.png', (0.40, 0.44, 0.18, 0.20), True),
    ('IMG20260824163810_640.png', 312, 'IMG20260824163810_640_rot312.png', (0.38, 0.38, 0.20, 0.18), False),
    ('IMG20260824164510_640.png', 'mirror', 'IMG20260824164510_640_mirror.png', (0.40, 0.52, 0.20, 0.22), False),
]

for src_name, angle, out_name, bbox, uncertain in linemark_jobs:
    src = base / src_name
    img = Image.open(src).convert('RGB')
    if angle == 'mirror':
        img = ImageOps.mirror(img)
    else:
        img = img.rotate(angle, expand=True, fillcolor=(255, 255, 255), resample=Image.Resampling.BICUBIC)

    final_path = out / out_name
    img.save(final_path)

    verdict = {
        'result': 'NEEDS_REVIEW' if uncertain else 'DEFECT',
        'defects': [{
            'category': 'line_mark',
            'severity': 3,
            'confidence': 0.55 if uncertain else 0.85,
            'display_name': 'Line Mark',
            'bbox': list(bbox),
        }],
    }
    ann_path = out / f'{final_path.stem}_ANNOTATED.png'
    renderer.render_annotated(str(final_path), verdict, str(ann_path))

print('Generated files:')
for p in sorted(out.iterdir()):
    print(p.name)
