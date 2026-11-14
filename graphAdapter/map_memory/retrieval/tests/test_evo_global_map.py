"""Whole-publication coverage and visual fallbacks on the RxR 2182 immutable pins."""
from contextlib import closing
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from graphAdapter.map_memory.retrieval.evo_global_map import _columns, _hull, render_global_map
from graphAdapter.map_memory.visualization import slice_points
from graphAdapter.map_memory.storage.store import load_episode

ROOT=Path('/data/zy/vln/case2')
MAP=ROOT/'outputs/graph_memory/candidate_detached_correction001-20261113/review/seal-profile/real-long-prefix/map'
PINS=['8615bc229e7d341c6583a10ff016e71bc6942be7049e4eb7147ab286e863e370',
      '48e22244a6f160d8df78a52f224ed2b5fc835c05c6feaada87ec98c470243939']


@pytest.mark.parametrize('pin',PINS)
def test_full_graph_and_next_frame(pin):
    with closing(load_episode(MAP,revision=pin)) as r:
        g=r._graph
        cap=r.cutoff['capture_seq'];uid=f"{r.identity['episode_uid']}:f{cap:06d}"
        im,p=render_global_map(r,uid)
        assert im.mode=='RGB' and im.size==(512,512) and sha256(im.tobytes()).hexdigest()==p['rgb_sha256']
        assert p['current_status']=='known'
        assert {v['uid'] for v in p['nodes']['views']}==set(g['views'])
        assert [a['uid'] for a in p['nodes']['anchors']]==g['scene_state']['anchor_keys']
        assert {(o['epoch'],o['id']) for o in p['nodes']['objects']}=={(e['epoch'],e['id']) for e in g['entities'] if e['status']=='active'}
        assert {(e['anchor_uid'],e['object_id']) for e in p['relations']['visibility']}==set(map(tuple,g['vsm']['visibility_edges']))
        assert {e['id'] for e in p['relations']['traversed']}=={e['id'] for e in g['edges'] if e['type']=='traversed'}
        assert p['coverage']['drawn_traversed']==9
        assert len(p['labels_in_plot'])==len(p['nodes']['anchors'])+len(p['nodes']['objects'])
        before=im.tobytes();im.putpixel((0,0),(0,0,0));p['nodes']['anchors'].clear()
        im,again=render_global_map(r,uid)
        assert im.tobytes()==before and len(again['nodes']['anchors'])==3
        im,other=render_global_map(r,f"{r.identity['episode_uid']}:f{cap+1:06d}")
        assert other['current_status']=='unknown' and other['rgb_sha256']!=again['rgb_sha256']
        # Empty the semantic layer in a detached metadata fixture; geometry and travel still exist.
        graph=deepcopy(g);graph['vsm']['anchors']={};graph['vsm']['visibility_edges']=[]
        graph['scene_state']['anchor_keys']=[];graph['entities']=[]
        proxy=SimpleNamespace(snapshot_id=pin,versions=r.versions,identity=r.identity,cutoff=r.cutoff,
                              _graph=graph,get_trace=r.get_trace,get_geometry=r.get_geometry)
        im,p=render_global_map(proxy,uid)
        assert im.size==(512,512) and p['coverage']['anchors']==p['coverage']['objects']==0
        assert set(p['labels_in_plot'])==set()
        graph['tiles']={}
        proxy.__dict__.pop('_evo_global_map_cache',None)
        im,p=render_global_map(proxy,uid)
        assert im is None and p['reason']=='no_geometry' and len(p['nodes']['views'])==cap


def test_projected_box_hull_removes_diagonals_and_interior():
    pts=[(0.,0.),(1.,1.),(0.,1.),(0.5,0.5),(1.,0.),(0.,0.)]
    assert _hull(pts)==[[0.,0.],[1.,0.],[1.,1.],[0.,1.]]


@pytest.mark.parametrize('pin',PINS)
def test_all_height_columns_match_original_slice_and_read_each_tile_once(pin,monkeypatch):
    with closing(load_episode(MAP,revision=pin)) as r:
        original=r.get_geometry
        reads=[]
        def capture(tid):
            reads.append(tid)
            return original(tid)
        monkeypatch.setattr(r,'get_geometry',capture)
        cells,flags,plane,coverage=_columns(r)
        assert reads==sorted(r._graph['tiles'])
        pts,states,reference=slice_points(r,'auto')
        assert plane['sampled_height_m']==reference['sampled_height_m']
        ref={}
        for key,value in zip(np.floor(pts[:,[0,2]]/plane['voxel_size_m']+.5).astype(int),states):
            key=tuple(key)
            ref[key]=ref.get(key,0)|int(value)
        assert ref=={tuple(k):int(f&3) for k,f in zip(cells,flags) if f&3}
        assert coverage['off_slice_only_cells']>0 and len(cells)==coverage['off_slice_only_cells']+len(ref)
        # Shift above all observations: footprint survives with no slice evidence.
        high=coverage['observed_height_range_m'][1]+10
        other,empty_flags,_,other_counts=_columns(r,height=high)
        assert np.array_equal(cells,other) and np.all(empty_flags==4)
        assert other_counts['tile_observed_voxels']==coverage['tile_observed_voxels']


def test_tile_cache_revalidates_pose_transform_height_identity_and_capacity(tmp_path):
    from graphAdapter.map_memory.retrieval.evo_global_map import MapTileColumns
    from graphAdapter.map_memory.storage.archive import IntegrityError,UnavailableMaterial
    from types import SimpleNamespace
    blob=tmp_path/'tile'
    blob.write_bytes(b'fixture')
    tiles={}
    arrays=dict(free_count=np.ones((2,2,2),dtype=np.uint32),surface_count=np.zeros((2,2,2),dtype=np.uint32))
    def make(tid):
        tiles[tid]=dict(pose_map_version=0,record=dict(blob=dict(path='tile'),meta=dict(T_G_L=np.eye(4).tolist())))
    make('a');make('b')
    r=SimpleNamespace(root=tmp_path,identity={'episode_uid':'ep'},versions={'pose_map_version':0},_graph={'tiles':tiles})
    def get_geometry(tid):
        return dict(arrays=arrays,metadata=tiles[tid]['record']['meta'])
    r.get_geometry=get_geometry
    cache=MapTileColumns(r,1)
    first=cache.read(r,'a',0.,.1)
    assert cache.read(r,'a',0.,.1) is first and cache.hits==1
    tiles['a']['record']['meta']['T_G_L'][0][3]=1.
    moved=cache.read(r,'a',0.,.1)
    assert np.array_equal(moved[0],first[0]+[10,0])
    cache.read(r,'a',10.,.1)
    tiles['a']['pose_map_version']=1
    with pytest.raises(IntegrityError,match='revision'):cache.read(r,'a',10.,.1)
    r.versions['pose_map_version']=1
    cache.read(r,'a',10.,.1)
    tiles['b']['pose_map_version']=1
    cache.read(r,'b',10.,.1)
    assert list(cache.items)==['b'] and cache.decodes==5
    cache.read(r,'a',10.,.1)
    assert cache.decodes==6
    blob.write_bytes(b'changed file')
    cache.read(r,'a',10.,.1)
    assert cache.decodes==7
    blob.unlink()
    with pytest.raises(UnavailableMaterial):cache.read(r,'a',10.,.1)
    r.identity['episode_uid']='other'
    with pytest.raises(IntegrityError,match='episode'):cache.read(r,'a',10.,.1)


@pytest.mark.parametrize('pin',['cb2b17e6f8f54ae8e84ee8106f357039414766a4375f65a604e9f59597b143fa',
                                '2567870ea84de8fabb34a6512263a97349aa7c3ba020152fa89b7a0550292ca5'])
def test_verified_map_without_eligible_historical_anchor(pin):
    from graphAdapter.map_memory.storage.decision_reads import _evo_witness
    from graphAdapter.map_memory.storage.archive import canonical,digest,IntegrityError
    from graphAdapter.map_memory.retrieval.contracts import MemoryQuery,CategoryVocabulary
    from graphAdapter.map_memory.retrieval.evo_material import read_evo_material
    from graphAdapter.map_memory.retrieval.evo_host import _upstream_path
    from graphAdapter.map_memory.retrieval.evo_global_map import global_map_caption
    from graphAdapter.map_memory.retrieval.host_input_compiler import pixel_hash
    with closing(load_episode(MAP,revision=pin)) as reader:
        ep=reader.identity['episode_uid'];seq=reader.cutoff['capture_seq'];uid=f'{ep}:f{seq:06d}'
        v=reader.get_retrieval_view(uid)
        query=MemoryQuery(ep,pin,uid,seq,seq,reader.cutoff['event_seq'],'Continue along the passage.',v.position,v.pose_map_version)
        vocab=CategoryVocabulary.from_file(ROOT/'vendor_sources/EvoMemNav/data/scannet200_classes.txt')
        with _upstream_path():material=read_evo_material(reader,query,vocab)
        image,manifest=render_global_map(reader,uid)
        compact={k:manifest[k] for k in ('schema_version','snapshot_id','episode_uid','cutoff','pose_map_version','current_uid','current_status','coverage','caption')}
        captions=[n['caption'] for n in manifest['nodes']['anchors']+manifest['nodes']['objects']]
        proof=dict(role='global',manifest=compact,full_manifest_hash=digest(canonical(manifest)),pixel_hash=pixel_hash(image),
                   caption=global_map_caption(manifest),node_captions=captions,omitted_node_count=0)
        claim=dict(request_id='early',episode_uid=ep,decision_id=1,event_seq=reader.cutoff['event_seq']+1,
                   frame_uid=uid,env_step=seq-1,snapshot_id=pin,summary=material['summary'],coverage=material['coverage'],
                   anchors=[],native_slots=8,attachment_slots=1,dropped=[],map_image=proof)
        assert material['coverage']['eligible_anchors']==0
        assert _evo_witness(reader,claim)['attachment_slots']==1
        with pytest.raises(IntegrityError):
            _evo_witness(reader,dict(claim,map_image=None,attachment_slots=0))
        with pytest.raises(IntegrityError):
            _evo_witness(reader,dict(claim,map_image=dict(proof,caption='Unverified caption')))

HISTORY='65262f87c9c94148294c057b97706f00213eaa677f1b8ef724f9a1ef1d7309e4'
LIVE='291e2a2bdfae5be416dcd2221d6d449d7474a98cedbd2791230ba3eec6f0e74b'

def test_live_camera_marker_is_separate_from_published_topology():
    from graphAdapter.map_memory.storage.archive import IntegrityError
    with closing(load_episode(MAP,revision=HISTORY)) as history, closing(load_episode(MAP,revision=LIVE)) as live:
        uid=f"{history.identity['episode_uid']}:f000038"
        checked=live.get_camera_pose_view(uid)
        assert live._SnapshotReader__graph is None and checked['frame_uid']==uid
        clock=live.cutoff['event_seq']+1
        historical,old=render_global_map(history,uid)
        image,new=render_global_map(history,uid,camera_source=LIVE,decision_event=clock)
        assert historical.tobytes()!=image.tobytes() and old['current_status']=='unknown'
        assert new['current_status']=='known' and new['nodes']==old['nodes'] and new['relations']==old['relations']
        assert new['cutoff']==old['cutoff'] and new['slice_sha256']==old['slice_sha256'] and new['coverage']==old['coverage']
        assert uid not in {v['uid'] for v in new['nodes']['views']}
        assert new['camera_overlay']['step']==37 and new['camera_overlay']['snapshot_id']==LIVE
        with pytest.raises(IntegrityError):render_global_map(history,uid,camera_source=LIVE,decision_event=live.cutoff['event_seq'])
        with pytest.raises(IntegrityError):render_global_map(history,uid+'x',camera_source=LIVE,decision_event=clock)
        same=render_global_map(live,uid)
        exact=render_global_map(live,uid,camera_source=LIVE,decision_event=clock)
        assert same[0].tobytes()==exact[0].tobytes() and same[1]==exact[1]


@pytest.mark.parametrize('fault',['session','transform','mount','source_frame','pose_revision','unavailable'])
def test_current_camera_never_uses_an_unverified_pose(monkeypatch,fault):
    from graphAdapter.map_memory.storage import store
    from graphAdapter.map_memory.storage.archive import IntegrityError
    from graphAdapter.map_memory.retrieval.evo_global_map import read_current_camera
    from graphAdapter.map_memory.retrieval.host_input_compiler import plain
    with closing(load_episode(MAP,revision=HISTORY)) as hist, closing(load_episode(MAP,revision=LIVE)) as src:
        uid=f"{hist.identity['episode_uid']}:f000038"
        row=plain(src.get_view(uid,include_images=False,include_depth=False))
        pose=row['capture']['pose_record']
        ver=dict(src.versions)
        if fault=='session':pose['episode_instance']='different'
        elif fault=='transform':row['T_G_cv']=np.array(row['T_G_cv']).copy();row['T_G_cv'][0,3]+=3
        elif fault=='mount':
            row['capture']['T_base_camera']=np.asarray(row['capture']['T_base_camera']).copy()
            row['capture']['T_base_camera'][1,3]+=.4
        elif fault=='source_frame':row['pose_binding']['source_frame_uid']='wrong'
        elif fault=='pose_revision':ver['pose_map_version']+=1
        elif fault=='unavailable':
            pose.update(valid=False,tracking_state='unavailable',geometry_status='unavailable',T_map_base=None,T_map_odom=None,T_odom_base=None,T_map_camera_cv=None)
        simulated=SimpleNamespace(identity=src.identity,cutoff=src.cutoff,versions=ver,snapshot_id=LIVE,
                                  get_camera_pose_view=lambda uid:row,close=lambda:None)
        monkeypatch.setattr(store,'load_episode',lambda *a,**k:simulated)
        if fault in ('unavailable','pose_revision'):
            ov=read_current_camera(hist,LIVE,uid,src.cutoff['event_seq']+1)
            assert ov['status']=='unknown' and 'xz' not in ov
        else:
            with pytest.raises((IntegrityError,ValueError)):read_current_camera(hist,LIVE,uid,src.cutoff['event_seq']+1)

@pytest.mark.parametrize('separate',[False,True])
def test_grounded_node_text_matches_camera_basis_and_real_visibility(separate):
    from graphAdapter.map_memory.retrieval.evo_global_map import global_map_caption
    from graphAdapter.map_memory.geometry.core import Q
    with closing(load_episode(MAP,revision=LIVE)) as live, closing(load_episode(MAP,revision=HISTORY if separate else LIVE)) as hist:
        uid=f"{live.identity['episode_uid']}:f000038"
        args=dict(camera_source=LIVE,decision_event=live.cutoff['event_seq']+1) if separate else {}
        _,new=render_global_map(hist,uid,grounded=True,**args)
        _,old=render_global_map(hist,uid,**args)
        assert new['relations']==old['relations'] and new['coverage']==old['coverage']
        assert new['current_step']==37 and new['current_status']=='known'
        assert f"Map through step {36 if separate else 37}." in global_map_caption(new)
        assert 'slot 8, step 37' in global_map_caption(new)
        camera=Q@np.asarray(live.get_camera_pose_view(uid)['capture']['pose_record']['T_map_camera_cv'])
        anchors={a['uid']:a for a in new['nodes']['anchors']}
        objects={(o['epoch'],o['id']):o for o in new['nodes']['objects']}
        edges={(e['anchor_uid'],e['object_epoch'],e['object_id']) for e in new['relations']['visibility']}
        for key,o in objects.items():
            observed=o['caption'].split('historical views: ')[1].split(', ')
            assert observed==[f"{a['id']} (step {a['step']})" for u,a in anchors.items() if (u,*key) in edges] or observed==['no anchor link'] and not any(e[1:]==key for e in edges)
            if o['xz'] is not None:
                # This actual pin uses level cameras. Recompute offsets independently using the inverse rigid transform.
                point=[o['xz'][0],camera[1,3],o['xz'][1],1.]
                x,_,z,_=np.linalg.solve(camera,point)
                for n,pos,neg in [(x,'right','left'),(z,'ahead','behind')]:
                    part=f'{abs(n):.1f} m '+(pos if n>0 else neg) if round(abs(n),1) else '0 m'
                    assert part in o['caption']
        for u,a in anchors.items():
            assert set(a['caption'].split('; saw ')[1].split(', '))==({objects[(epoch,oid)]['map_id'] for frame,epoch,oid in edges if frame==u} or {'none recorded'})
            assert a['step']<=hist.cutoff['capture_seq']-1
        assert not separate or uid not in anchors

def test_source_labels_follow_frames_and_native_object_ids_under_reordering():
    from graphAdapter.map_memory.retrieval.evo_global_map import _inventory
    from graphAdapter.map_memory.storage.archive import IntegrityError
    with closing(load_episode(MAP,revision=HISTORY)) as rd:
        graph=deepcopy(rd._graph)
        def inv():
            proxy=SimpleNamespace(_graph=graph,cutoff=rd.cutoff,versions=rd.versions)
            nodes,_=_inventory(proxy,source_labels=True)
            return ({a['uid']:a['id'] for a in nodes['anchors']},{o['id']:o['map_id'] for o in nodes['objects']})
        a,o=inv()
        assert a and o and all(tag==f'O{oid}' for oid,tag in o.items())
        graph['scene_state']['anchor_keys'].reverse()
        assert inv()==(a,o)
        # Keep the same epoch and remove the smallest native ID from a detached fixture.
        oid=min(o)
        graph['entities']=[e for e in graph['entities'] if e['id']!=oid]
        for node in graph['vsm']['anchors'].values():node['objects']=[v for v in node['objects'] if v!=oid]
        graph['vsm']['visibility_edges']=[edge for edge in graph['vsm']['visibility_edges'] if edge[1]!=oid]
        assert inv()==(a,{k:v for k,v in o.items() if k!=oid})
        graph['scene_state']['epoch']='another-epoch'
        with pytest.raises(IntegrityError):inv()


def test_audit_rejects_labels_swapped_between_real_anchor_headers():
    from graphAdapter.evaluation.evo_material_audit import verify_source_node_references
    anchors=[dict(room='hallway',step=n,evidence=[]) for n in (3,6)]
    def caption(tags):
        return chr(10).join(f"Anchor View {j} (room: hallway; observed at step {n}; historical full view)."+chr(10)
                            +f"Map node A{tag} is the observing camera for this group."
                            for j,(n,tag) in enumerate(zip((3,6),tags)))
    verify_source_node_references(caption((3,6)),anchors,'epoch')
    with pytest.raises(ValueError):verify_source_node_references(caption((6,3)),anchors,'epoch')
