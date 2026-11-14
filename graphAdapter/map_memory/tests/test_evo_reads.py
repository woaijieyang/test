"""A sealed Evo claim must survive independent checks against a real decision-time publication."""
from contextlib import closing
from copy import deepcopy
from pathlib import Path

import pytest

from graphAdapter.map_memory.retrieval.contracts import CategoryVocabulary
from graphAdapter.map_memory.retrieval.protocol import native_slot_indices
from graphAdapter.map_memory.storage.archive import IntegrityError
from graphAdapter.map_memory.storage.decision_reads import _evo_witness, decision_reads
from graphAdapter.map_memory.storage.store import load_episode

ROOT = Path("/data/zy/vln/case2")
MAP = ROOT / "outputs/graph_memory/candidate_detached_correction001-20261113/review/seal-profile/real-long-prefix/map"
PIN = "8615bc229e7d341c6583a10ff016e71bc6942be7049e4eb7147ab286e863e370"


def test_evo_claim_against_pinned_sources_and_same_count_tampering():
    from graphAdapter.map_memory.retrieval.evo_host import _upstream_path
    from graphAdapter.map_memory.retrieval.contracts import MemoryQuery
    from graphAdapter.map_memory.retrieval.evo_material import read_evo_material
    vocab = CategoryVocabulary.from_file(ROOT/"vendor_sources/EvoMemNav/data/scannet200_classes.txt")
    with closing(load_episode(MAP,revision=PIN)) as reader:
        seq = reader.cutoff['capture_seq']
        uid = next(u for u,v in reader._graph['views'].items() if v['capture_seq'] == seq)
        query = MemoryQuery(reader.identity['episode_uid'],PIN,uid,seq,seq,reader.cutoff['event_seq'],"continue")
        with _upstream_path():
            material = read_evo_material(reader,query,vocab)
        native = {step:j for j,step in enumerate(native_slot_indices(seq,8),1)}
        anchors = [dict(a,native_slot=native.get(a['step'])) for a in material['anchors']]
        claim = dict(kind='EvoTopologyCompiled',request_id='real-pin',decision_id=9,episode_uid=query.episode_uid,
                     frame_uid=uid,env_step=seq-1,snapshot_id=PIN,event_seq=reader.cutoff['event_seq']+1,
                     summary=material['summary'],coverage=material['coverage'],anchors=anchors,dropped=[],
                     native_slots=8,attachment_slots=sum(len(a['evidence'])+(a['native_slot'] is None) for a in anchors))
        (kind, selected), = decision_reads([claim])
        proof = _evo_witness(reader,selected)
        assert kind == 'evo_reads'
        assert proof['pin'] == PIN and proof['compiled_anchor_count'] == len(anchors)
        crop = next(c for a in proof['anchors'] for c in a['evidence'] if c['object_id'] == 9)
        assert crop['label'] == 'column' and len(crop['raw_xyxy']) == 4
        for field,value in [('member','alien:d00000'),('prompt_row',-1),('index',False),('label','different'),
                            ('object_epoch','other'),('box_xyxy',[0,0,1,1]),('aggregate_label','other')]:
            invalid = deepcopy(selected)
            next(c for a in invalid['anchors'] for c in a['evidence'] if c['object_id']==9)[field] = value
            with pytest.raises(IntegrityError):
                _evo_witness(reader,invalid)
        for field,value in [('summary','Rooms(now): fabricated:A1/F0/O1'),('snapshot_id','different'),
                            ('attachment_slots',selected['attachment_slots']+1)]:
            with pytest.raises(IntegrityError):
                _evo_witness(reader,dict(selected,**{field:value}))
        invalid = deepcopy(selected)
        invalid['coverage']['entities'] += 1
        with pytest.raises(IntegrityError):
            _evo_witness(reader,invalid)
        with pytest.raises(IntegrityError):
            list(decision_reads([claim,claim]))


def test_failed_witness_preserves_source_and_does_not_publish_stream(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from graphAdapter.map_memory.storage import decision_reads as module
    work = tmp_path/'work'
    root = work/'history'
    root.mkdir(parents=True)
    (root/'CURRENT.json').write_text('original source')
    result = tmp_path/'result'
    result.mkdir()
    opened = []
    def load(root,revision):
        opened.append(revision)
        return SimpleNamespace(close=lambda:None)
    def damaged(reader,claim):
        raise IntegrityError('submitted source differs')
    monkeypatch.setattr(module, 'load_episode', load)
    with pytest.raises(IntegrityError, match='submitted source differs'):
        module._seal_witnesses(root,work,result,'evo_reads',[dict(snapshot_id='original-pin')],
                               damaged,dict(max_trace_raw_bytes=4096,max_trace_compressed_bytes=4096))
    assert opened == ['original-pin']
    assert (root/'CURRENT.json').read_text() == 'original source'
    assert list(result.iterdir()) == []
    assert list(work.iterdir()) == [root]
