"""Run the production GroundedInspector pipeline end to end."""
from __future__ import annotations
import argparse, os
from typing import List
from . import renderer
from .inspection import pipeline

_EXTS=(".png",".jpg",".jpeg",".PNG",".JPG",".JPEG")
DEFAULT_MODEL=os.environ.get("ANTHROPIC_MODEL","claude-sonnet-4-5")

def _iter_images(folder:str)->List[str]:
    return sorted(os.path.join(folder,f) for f in os.listdir(folder) if os.path.splitext(f)[1] in _EXTS)

def inspect_image(part, image_path, model):
    """Single public inspection entry point; both explicit and auto use the modular pipeline."""
    return pipeline.inspect_part(part,image_path,model) if part else pipeline.inspect_auto(image_path,model)

def main(argv=None)->int:
    ap=argparse.ArgumentParser(description=__doc__)
    g=ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--part",help="canonical part name (for example bracket)")
    g.add_argument("--auto",action="store_true",help="identify all configured part instances")
    src=ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--image",help="single input image path")
    src.add_argument("--folder",help="folder of input images")
    ap.add_argument("--model",default=DEFAULT_MODEL,help=f"vision model (default {DEFAULT_MODEL})")
    ap.add_argument("--out",help="output path (single-image mode only)")
    args=ap.parse_args(argv)
    targets=[args.image] if args.image else _iter_images(args.folder)
    if not targets: ap.error("no images found to inspect")
    out_dir=os.path.join(args.folder,"annotated") if args.folder else (os.path.dirname(args.out) if args.out else os.path.join(os.path.dirname(args.image) or ".","annotated"))
    os.makedirs(out_dir,exist_ok=True)
    for src_path in targets:
        verdict=inspect_image(None if args.auto else args.part,src_path,args.model)
        stem=os.path.splitext(os.path.basename(src_path))[0]
        out=args.out if args.image and args.out else os.path.join(out_dir,f"{stem}_ANNOTATED.png")
        renderer.render_annotated(src_path,verdict,out)
        if args.auto:
            cats=", ".join(sorted({d["category"] for i in verdict.get("instances",[]) for d in i.get("defects",[])})) or "-"
            order={"DEFECT":0,"NEEDS_REVIEW":1,"OK":2}
            result=min((i.get("result","NEEDS_REVIEW") for i in verdict.get("instances",[])),key=lambda r:order.get(r,3),default="NEEDS_REVIEW")
        else:
            cats=", ".join(sorted({d["category"] for d in verdict.get("defects",[])})) or "-"
            result=verdict.get("result","NEEDS_REVIEW")
        print(f"{result:<12} {stem}  [{cats}]")
    print(f"Inspected {len(targets)} image(s); annotated -> {out_dir}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
