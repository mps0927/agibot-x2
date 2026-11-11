"""Persist the exact VLM input image once per request; never store API headers."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,uuid

def save_json(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def begin_run(root,frame,data):
    now=datetime.now(timezone.utc)
    run_id=now.strftime('%Y%m%dT%H%M%S_%fZ_')+uuid.uuid4().hex[:8]
    folder=Path(root)/run_id;folder.mkdir(parents=True,exist_ok=False)
    jpeg=frame.get('jpeg')
    if jpeg is not None:(folder/'input.jpg').write_bytes(jpeg)
    manifest=dict(schema='x2.vlm.run.v1',run_id=run_id,requested_at_utc=now.isoformat(),
        image_file='input.jpg' if jpeg is not None else None,image_available=jpeg is not None,
        image_sha256=hashlib.sha256(jpeg).hexdigest() if jpeg is not None else None,
        original_frame_metadata=frame['meta'],events=[])
    save_json(folder/'run_manifest.json',manifest)
    save_json(folder/'instruction.json',dict(instruction=data.get('instruction'),model=data.get('model'),execute_requested=data.get('execute_requested') is True))
    return dict(run_id=run_id,directory=str(folder),image_path=str(folder/'input.jpg') if jpeg is not None else None,
                manifest_path=str(folder/'run_manifest.json'))
