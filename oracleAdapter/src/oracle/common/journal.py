"""Append-only hash-chained result segments with evidence-preserving recovery.

The caller must hold an exclusive controller lock. This class never determines
worker ownership or rerun eligibility; those belong to the full-run controller.
"""
import json
import os
from pathlib import Path
from oracle.common.artifacts import content_digest,digest,write_json


class ResultJournal:
    def __init__(self,folder):
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True)
        self.records={};self.sequence=0;self.previous='0'*64;self.recovered_tails=[]
        files=sorted(self.folder.glob('segment-*.jsonl'))
        for ordinal,path in enumerate(files):
            data=path.read_bytes();offset=0
            for line in data.splitlines(keepends=True):
                if not line.endswith(b'\n'):
                    marker=path.with_suffix('.torn.json')
                    observation={'segment':path.name,'segment_sha256':digest(path),'offset':offset,'bytes':len(line),
                                 'tail_sha256':__import__('hashlib').sha256(line).hexdigest(),
                                 'action':'Retained verbatim; no in-place truncation; new writes use another segment'}
                    if marker.exists():
                        if json.loads(marker.read_text())!=observation:raise ValueError('Previously sealed torn tail changed')
                    elif ordinal==len(files)-1:
                        write_json(marker,observation)
                    else:raise ValueError('Unexplained incomplete non-final segment')
                    self.recovered_tails.append(observation)
                    break
                try:entry=json.loads(line)
                except (ValueError,UnicodeError) as exc:raise ValueError('Corrupt complete journal record') from exc
                self._accept(entry)
                offset+=len(line)
        number=int(files[-1].stem.split('-')[-1])+1 if files else 1
        self.path=self.folder/f'segment-{number:06}.jsonl'
        self.stream=self.path.open('xb')

    def _accept(self,entry):
        if set(entry)!={'seq','prev','key','payload','entry_sha256'}:raise ValueError('Unexpected journal schema')
        core={k:v for k,v in entry.items() if k!='entry_sha256'}
        if entry['seq']!=self.sequence+1 or entry['prev']!=self.previous or content_digest(core)!=entry['entry_sha256']:
            raise ValueError('Journal chain or sequence mismatch')
        key=entry['key']
        if not isinstance(key,str) or not key or key in self.records:raise ValueError('Duplicate/invalid execution key')
        self.records[key]=entry['payload'];self.sequence+=1;self.previous=entry['entry_sha256']

    def append(self,key,payload):
        if key in self.records:raise ValueError('Execution already recorded; never overwrite an outcome')
        core={'seq':self.sequence+1,'prev':self.previous,'key':key,'payload':payload}
        entry={**core,'entry_sha256':content_digest(core)}
        raw=(json.dumps(entry,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n').encode('utf-8')
        # Validate and own a detached payload before committing a durable frame.
        detached=json.loads(raw)
        if not isinstance(key,str) or not key:raise ValueError('Invalid execution key')
        self.stream.write(raw);self.stream.flush();os.fsync(self.stream.fileno())
        self._accept(detached)
        return detached['entry_sha256']

    def close(self):
        self.stream.close()

    def __enter__(self):return self
    def __exit__(self,*_):self.close()
