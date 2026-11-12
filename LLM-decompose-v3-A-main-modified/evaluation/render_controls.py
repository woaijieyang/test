"""Create diagnostic seam alternatives on ONE frozen candidate, no performance selection.
These variants are NOT eligible for commit under the frozen LF review receipt.
"""
from __future__ import annotations
from renderer.freeze import FrozenCandidate
from contracts.common import sha_text

def variants(frozen: FrozenCandidate) -> list[dict]:
    frozen.verify();p=frozen.plan();c=frozen.candidate()
    if frozen.mode=='SOURCE_EXACT':
        return [{'policy':'SOURCE_EXACT','instruction':frozen.instruction,'sha256':frozen.instruction_sha256,'status':'NOT_RUN'}]
    out=[]
    for name,sep in [('LF','\n'),('ASCII_SPACE',' '),('LEGACY_TIGHT','')]:
        # Joining logical strings never removes a native LF/CRLF within a copied stage.
        text=p['source_prefix']+sep.join(c['subtasks'])+p['source_suffix']
        out.append({'policy':name,'instruction':text,'sha256':sha_text(text),'status':'NOT_RUN',
                    'note':'Diagnostic input, not approved by the original receipt. Do not select a per-episode winner using outcomes.'})
    return out
