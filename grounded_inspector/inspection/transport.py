"""Model transport shared by inspection stages."""
from __future__ import annotations
import base64, io, json, os, sys
from typing import List, Tuple
_MEDIA={".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg"}
_INTERACTIVE_ENV="GROUNDED_INSPECTOR_TRANSPORT"
_REQUEST_MARKER="GROUNDED_INSPECTOR_REQUEST "
def encode_image(path:str)->dict:
    ext=os.path.splitext(path)[1].lower()
    with open(path,"rb") as fh: data=fh.read()
    from PIL import Image
    with Image.open(io.BytesIO(data)) as im:
        if max(im.size)>2000:
            im.thumbnail((2000,2000),Image.Resampling.LANCZOS); out=io.BytesIO(); im.save(out,format="PNG" if ext==".png" else "JPEG",quality=95); data=out.getvalue()
    return {"type":"image","source":{"type":"base64","media_type":_MEDIA.get(ext,"image/png"),"data":base64.standard_b64encode(data).decode("ascii")}}
def _call_model_anthropic(prompt:str,images:List[Tuple[str,str]],model:str)->dict:
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
def _validate_interactive_reply(reply:dict)->None:
    """Fail fast instead of letting a malformed DEFECT reply silently become OK.
    aggregator.py only renders defects that carry a non-empty `locations` list
    with a real bbox; a DEFECT status without one is dropped without error."""
    if reply.get("status")!="DEFECT" or "defect" not in reply:
        return  # anatomy replies (no "defect" key) and CLEAR/NEEDS_REVIEW carry no locations.
    locations=reply.get("locations")
    if not isinstance(locations,list) or not locations:
        raise ValueError(f"Interactive reply has status=DEFECT but no locations (would silently render as OK): {reply}")
    for loc in locations:
        bbox=loc.get("bbox") if isinstance(loc,dict) else None
        if not (isinstance(bbox,list) and len(bbox)==4 and all(isinstance(v,(int,float)) for v in bbox)):
            raise ValueError(f"Interactive reply has an invalid/missing bbox in locations: {loc}")
def _call_model_interactive(prompt:str,images:List[Tuple[str,str]],model:str)->dict:
    """Development-time transport: blocks on stdin instead of calling Anthropic.
    Prints one self-contained JSON request line, then reads one JSON response
    line. Lets a human/agent at the terminal act as the model, through the
    unmodified pipeline/anatomy/defect/aggregator/renderer call graph."""
    request={"model":model,"prompt":prompt,"images":[{"label":label,"path":path} for label,path in images]}
    print(_REQUEST_MARKER+json.dumps(request,ensure_ascii=False),flush=True)
    line=sys.stdin.readline()
    if not line: raise RuntimeError("Interactive transport: no response received on stdin (EOF).")
    line=line.strip()
    start,end=line.find("{"),line.rfind("}")
    if start<0 or end<0: raise ValueError(f"No JSON object found in interactive reply:\n{line[:400]}")
    reply=json.loads(line[start:end+1])
    _validate_interactive_reply(reply)
    return reply
def call_model(prompt:str,images:List[Tuple[str,str]],model:str)->dict:
    if os.environ.get(_INTERACTIVE_ENV)=="interactive":
        return _call_model_interactive(prompt,images,model)
    return _call_model_anthropic(prompt,images,model)
