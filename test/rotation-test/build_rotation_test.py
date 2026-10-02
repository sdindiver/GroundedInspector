from pathlib import Path
from PIL import Image, ImageOps
import shutil

base = Path(r'c:\workspace-ai\images_640\bracket')
out = base / 'rotation_test'
if out.exists():
    shutil.rmtree(out)
out.mkdir(parents=True, exist_ok=True)

jobs = [
    ('IMG20260824163907_640.png', 143, 'IMG20260824163907_640_rot143.png', 'IMG20260824163907_640_ANNOTATED.png'),
    ('IMG20260824164818_640.png', None, 'IMG20260824164818_640_mirror.png', 'IMG20260824164818_640_ANNOTATED.png', 'mirror'),
    ('IMG20260824165152_640.png', 68, 'IMG20260824165152_640_rot68.png', 'IMG20260824165152_640_ANNOTATED.png'),
    ('IMG20260824164116_640.png', 291, 'IMG20260824164116_640_rot291.png', 'IMG20260824164116_640_ANNOTATED.png'),
]

for job in jobs:
    src_name, angle, out_name, ann_name, *rest = job

    img = Image.open(base / src_name).convert('RGB')
    ann = Image.open(base / 'annotated' / ann_name).convert('RGBA')

    if rest and rest[0] == 'mirror':
        img = ImageOps.mirror(img)
        ann = ImageOps.mirror(ann)
    else:
        img = img.rotate(angle, expand=True, fillcolor=(255, 255, 255), resample=Image.Resampling.BICUBIC)
        ann = ann.rotate(angle, expand=True, fillcolor=(255, 255, 255, 0), resample=Image.Resampling.BICUBIC)

    img.save(out / out_name)
    ann.save(out / f"{Path(out_name).stem}_ANNOTATED.png")

print('created:')
for p in sorted(out.iterdir()):
    print(p.name)
