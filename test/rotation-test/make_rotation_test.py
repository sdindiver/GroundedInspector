from pathlib import Path
from PIL import Image, ImageOps
import shutil

base = Path(r'c:\workspace-ai\images_640\bracket')
out = base / 'rotation_test'
if out.exists():
    shutil.rmtree(out)
out.mkdir(parents=True, exist_ok=True)

jobs = [
    ('IMG20260824163907_640.png', 143, 'IMG20260824163907_640_rot143.png'),
    ('IMG20260824164818_640.png', None, 'IMG20260824164818_640_mirror.png', 'mirror'),
    ('IMG20260824165152_640.png', 68, 'IMG20260824165152_640_rot68.png'),
    ('IMG20260824164116_640.png', 291, 'IMG20260824164116_640_rot291.png'),
]

for job in jobs:
    src = job[0]
    angle = job[1]
    name = job[2]
    img = Image.open(base / src).convert('RGB')
    if len(job) > 3 and job[3] == 'mirror':
        img = ImageOps.mirror(img)
    else:
        img = img.rotate(angle, expand=True, fillcolor=(255, 255, 255), resample=Image.Resampling.BICUBIC)
    img.save(out / name)

print('created:')
for p in sorted(out.iterdir()):
    print(p.name)
