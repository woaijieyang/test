"""Read sealed trace rows and compare source pixels."""
import gzip,json,hashlib
import numpy as np
def rows(path):
    with gzip.open(path,'rt') as stream:
        return [json.loads(line) for line in stream]

def index(data,kind,key):
    items=[v for v in data if v['kind']==kind]
    by_id={v[key]:v for v in items}
    if len(by_id)!=len(items):
        raise ValueError(f'Duplicate {kind} identity')
    return by_id

def hash_pixels(image):
    pixels=image.tobytes()
    host=hashlib.sha256(image.mode.encode()+str(image.size).encode()+pixels).hexdigest()
    basis=json.dumps({'dtype':'|u1','shape':[image.height,image.width,3]},sort_keys=True,separators=(',',':')).encode()
    return host,hashlib.sha256(basis+pixels).hexdigest()

