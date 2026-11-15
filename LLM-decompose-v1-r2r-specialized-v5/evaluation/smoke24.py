"""Check renderer on the attachment's 24 case texts. Does not run language/nav models."""
import json
from adapter.source import Source
from renderer.freeze import freeze,unchanged
from host.compile import ROOT

def smoke():
    result=[]
    for c in json.loads((ROOT/'evaluation/source_cases.json').read_bytes()):
        ds=c['dataset'];parts=c['current_subtasks'] if ds=='R2R' else c['old_subtasks'];s=Source(c['id'],ds,'en' if ds=='R2R' else 'en-US',c['source']);v=freeze(s,parts) if parts else unchanged(s)
        assert len(v.stages)==(len(parts) or 1)
        result.append({'dataset':ds,'id':c['id'],'supplied_stage_count':len(parts),'mode':v.mode,'source_sha256':s.sha,'preview_sha256':v.sha,'frozen_stage_text_differs_from_proposal':bool(parts) and list(v.stages)!=parts,'scope':'supplied strings -> formatter only; not semantic re-evaluation or a repeat navigation'})
    return result
if __name__=='__main__':
    out=smoke();(ROOT/'evaluation/renderer_smoke24.json').write_text(json.dumps(out,indent=2)+'\n');print(f'{len(out)} cases processed')
