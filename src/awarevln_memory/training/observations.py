"""CPU audit of real RGB assets; unavailable frames remain a repair queue.

Repeated paths are legal for the native eight-frame sampler. This audit does
not claim semantic correctness of actions, grounding or a rollout outcome.
"""
from pathlib import Path
from PIL import Image
from .artifacts import training_path,digest


def audit_observations(events):
    files={};ready=[];repairs=[]
    for original in events:
        event=dict(original);errors=[]
        if event.get('source_split')!='train':
            raise ValueError('evaluation observations cannot enter a training asset audit')
        paths=event.get('image_paths',[])
        if len(paths)!=8 or event.get('prompt','').count('<image>')!=8:
            errors.append({'reason':'NATIVE_EIGHT_FRAME_LAYOUT_MISSING'})
        records=[]
        for slot,raw in enumerate(paths):
            # Evaluation-root violations are fatal, not recoverable missing files.
            path=training_path(raw);key=str(path)
            if key not in files:
                try:
                    with Image.open(path) as image:
                        size=list(image.size);image.verify()
                    if min(size)<1:raise ValueError('empty image')
                    files[key]={'path':key,'sha256':digest(path),'size':size,'valid':True}
                except (OSError,ValueError) as exc:
                    files[key]={'path':key,'valid':False,'reason':type(exc).__name__,'detail':str(exc)}
            record=files[key];records.append(record)
            if not record['valid']:errors.append({'slot':slot,'path':key,'reason':'MISSING_OR_INVALID_IMAGE'})
        if errors:
            repairs.append({'event_id':event.get('event_id'),'errors':errors,'action':'repair_frames_then_reaudit'})
        else:
            event['image_asset_checks']=[{'sha256':x['sha256'],'size':x['size']} for x in records]
            ready.append(event)
    report={'input_events':len(events),'ready_events':len(ready),'repairable_events':len(repairs),
            'unique_files':len(files),'valid_unique_files':sum(x['valid'] for x in files.values()),
            'scope':'RGB_DECODE_AND_SOURCE_ONLY_NOT_LABEL_OR_NAVIGATION_ACCEPTANCE'}
    return ready,repairs,list(files.values()),report
