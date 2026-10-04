"""Model transport shared by inspection stages."""
from __future__ import annotations
import base64, io, json, os
from typing import List, Tuple
_MEDIA={".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg"}
def encode_image(path:str)->dict:
    ext=os.path.splitext(path)[1].lower()
    with open(path,"rb") as fh: data=fh.read()
    from PIL import Image
    with Image.open(io.BytesIO(data)) as im:
        if max(im.size)>2000:
            im.thumbnail((2000,2000),Image.Resampling.LANCZOS); out=io.BytesIO(); im.save(out,format="PNG" if ext==".png" else "JPEG",quality=95); data=out.getvalue()
    return {"type":"image","source":{"type":"base64","media_type":_MEDIA.get(ext,"image/png"),"data":base64.standard_b64encode(data).decode("ascii")}}
def call_model(prompt:str,images:List[Tuple[str,str]],model:str)->dict:
    try:
        import truststore; truststore.inject_into_ssl(); import anthropic
    except ImportError as exc: raise RuntimeError("API dependencies are not installed. Run: pip install -r requirements.txt") from exc
    if not os.environ.get("ANTHROPIC_API_KEY"): raise RuntimeError("ANTHROPIC_API_KEY is not set.")
    content=[{"type":"text","text":prompt}]
    for label,path in images: content += [{"type":"text","text":f"[{label}]"},encode_image(path)]
    msg=anthropic.Anthropic().messages.create(model=model,max_tokens=3000,messages=[{"role":"user","content":content}])
    text="".join(b.text for b in msg.content if getattr(b,"type","")=="text").strip(); start,end=text.find("{"),text.rfind("}")
    if start<0 or end<0: raise ValueError(f"No JSON object found in engine reply:\n{text[:400]}")
    return json.loads(text[start:end+1])
