"""Read the real RxR 2182 decisions without a simulator or writes to the episode."""
from contextlib import closing
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from graphAdapter.map_memory.retrieval.contracts import CategoryVocabulary,MemoryQuery
from graphAdapter.map_memory.retrieval.evo_material import read_evo_material
from graphAdapter.map_memory.retrieval.evo_map_image import render_evo_map
from graphAdapter.map_memory.storage.store import IntegrityError,load_episode

ROOT=Path('/data/zy/vln/case2')
MAP=ROOT/'outputs/graph_memory/candidate_detached_correction001-20261113/review/seal-profile/real-long-prefix/map'
PINS=['8615bc229e7d341c6583a10ff016e71bc6942be7049e4eb7147ab286e863e370',
      '48e22244a6f160d8df78a52f224ed2b5fc835c05c6feaada87ec98c470243939']


@pytest.mark.parametrize('pin',PINS)
def test_pinned_map(pin,monkeypatch):
    vocab=CategoryVocabulary.from_file(ROOT/'vendor_sources/EvoMemNav/data/scannet200_classes.txt')
    with closing(load_episode(MAP,revision=pin)) as reader:
        cap=reader.cutoff['capture_seq']
        ep=reader.identity['episode_uid']
        uid=f'{ep}:f{cap:06d}'
        q=MemoryQuery(ep,pin,uid,cap,cap,reader.cutoff['event_seq'],'turn at the door')
        groups=read_evo_material(reader,q,vocab)['anchors']
        image,p=render_evo_map(reader,groups,uid)
        assert image.size==(512,512) and image.mode=='RGB'
        assert sha256(image.tobytes()).hexdigest()==p['rgb_sha256']
        assert p['snapshot_id']==pin and p['traversed_edges']==9
        assert [a['room'] for a in p['anchors']]==[a['room'] for a in groups]
        assert p['current_status']=='known'
        assert p['objects'] and all(o['members'] for o in p['objects'])
        assert sum(p['slice_cells'].values())>0
        before=image.tobytes()
        image.putpixel((0,0),(0,0,0))
        p['anchors'].clear()
        cached,proof=render_evo_map(reader,groups,uid)
        assert cached.tobytes()==before and proof['anchors']
        other,absent=render_evo_map(reader,groups,f'{ep}:f{cap+1:06d}')
        assert absent['current_status']=='unknown' and absent['current_camera'] is None
        assert absent['rgb_sha256']!=proof['rgb_sha256'] and other.size==(512,512)
        wrong=deepcopy(groups)
        det=next(c for a in wrong for c in a['evidence'])
        det['member']='other:d00001'
        with pytest.raises(IntegrityError):
            render_evo_map(reader,wrong,uid)
        assert render_evo_map(reader,[],uid)[1]['reason']=='no_selected_anchors'
