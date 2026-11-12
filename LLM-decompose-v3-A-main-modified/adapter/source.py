"""Own source identity and source-format profiles. Never edit instruction text."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Mapping
import re
from contracts.common import require, sha_text, sha_obj

@dataclass(frozen=True)
class SourceRecord:
    task_key: str
    dataset: str
    language: str
    original_instruction: str
    source_sha256: str
    record_identity_sha256: str
    prefix: str
    body: str
    suffix: str
    body_start: int
    body_end: int

    def __post_init__(self):
        s=self.original_instruction
        require(isinstance(s,str) and bool(s.strip()),'Invalid source text')
        require(self.source_sha256==sha_text(s),'SourceRecord hash mismatch')
        require(self.prefix+self.body+self.suffix==s,'SourceRecord envelope mismatch')
        require(type(self.body_start) is int and type(self.body_end) is int and self.body_start==len(self.prefix) and self.body_end==len(self.prefix)+len(self.body),'SourceRecord span mismatch')
        require(self.record_identity_sha256==sha_obj({'task_key':self.task_key,'dataset':self.dataset,'language':self.language,'source_sha256':self.source_sha256}),'SourceRecord identity mismatch')

    def model_input(self) -> dict[str,str]:
        # Strictly source-only route evidence: no score, GT, scene or another record.
        return {'original_instruction':self.original_instruction}

    def profile(self) -> dict[str,Any]:
        s=self.original_instruction;b=self.body
        return {'dataset':self.dataset,'language':self.language,'codepoints':len(s),'utf8_bytes':len(s.encode('utf-8')),
                'prefix_repr':repr(self.prefix),'suffix_repr':repr(self.suffix),
                'body_multiple_ASCII_spaces':bool(re.search(r' {2,}',b)),
                'any_multiple_ASCII_spaces':bool(re.search(r' {2,}',s)),
                'body_LF':b.count('\n'),'suffix_LF':self.suffix.count('\n'),
                'CRLF':s.count('\r\n'),'bare_LF':s.count('\n')-s.count('\r\n'),
                'TAB':s.count('\t'),'literal_backslash_n':s.count('\\n'),
                'non_ASCII':sorted({f'U+{ord(c):04X}' for c in s if ord(c)>127}),
                'source_sha256':self.source_sha256,'record_identity_sha256':self.record_identity_sha256}

def ingest(data: Mapping[str,Any]) -> SourceRecord:
    require(isinstance(data,Mapping),'Source record must be an object')
    data=dict(data)
    available=[]
    for name in ('original_instruction','instruction_text'):
        if name in data:available.append(data[name])
    nested=data.get('instruction')
    if isinstance(nested,Mapping) and 'instruction_text' in nested:available.append(nested['instruction_text'])
    require(bool(available) and all(isinstance(x,str) and x==available[0] for x in available),'Missing or conflicting raw instruction fields')
    data['original_instruction']=available[0]
    if isinstance(data.get('dataset'),str):data['dataset']=data['dataset'].lower()

    # Do not infer a different dataset/language or a missing ID.
    required=['task_key','dataset','language','original_instruction']
    require(all(k in data for k in required),'missing source record fields')
    task,ds,lang,text=(data[k] for k in required)
    require(all(isinstance(x,str) for x in [task,ds,lang,text]),'source fields must be strings')
    require(bool(task.strip()) and bool(text.strip()),'task identity and nonblank source required')
    require((ds,lang) in {('r2r','en'),('rxr','en-US')},'only R2R en and RxR en-US are in scope')
    text.encode('utf-8',errors='strict')
    left=len(text)-len(text.lstrip());right=len(text.rstrip())
    sha=sha_text(text)
    for field in ('original_instruction_sha256','source_sha256'):
        require(field not in data or data[field]==sha, 'Supplied source hash disagrees with raw instruction')
    if 'instruction_text' in data:require(data['instruction_text']==text,'Conflicting source text fields')
    return SourceRecord(task,ds,lang,text,sha,sha_obj({'task_key':task,'dataset':ds,'language':lang,'source_sha256':sha}),text[:left],text[left:right],text[right:],left,right)
