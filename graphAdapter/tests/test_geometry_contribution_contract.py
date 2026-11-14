import numpy as np
from graphAdapter.map_memory.geometry.core import TSDFTile
from graphAdapter.map_memory.geometry.contribution_contract import exact_write_contract

def tile():
    return TSDFTile('test',np.array([[-.5,.5],[-.5,.5],[-.5,.5]]),.1,np.eye(4),base_position_L=np.zeros(3),near_m=0.,far_m=10.)

def test_equal_exact_write_contracts_reproduce_all_tile_arrays():
    rgb=np.zeros((16,16,3),np.uint8);depth=np.full((16,16),2.,np.float32);mask=np.ones((16,16),bool)
    k=np.array([[8.,0,7.5],[0,8.,7.5],[0,0,1.]])
    a=tile();b=tile();pose=np.eye(4);pose[:3,3]=[.013,.027,.019];changed=pose.copy();changed[0,3]+=1e-12
    assert exact_write_contract(a,depth,mask,k,pose)==exact_write_contract(b,depth,mask,k,changed)
    for n in range(3):
        a.integrate(str(n),rgb,depth,mask,k,pose,source_hash='source')
        b.integrate(str(n),rgb,depth,mask,k,changed,source_hash='source')
    assert all(np.array_equal(value,b.arrays()[name]) for name,value in a.arrays().items())

def test_changed_write_set_is_not_certified_by_small_pose_label():
    a=tile();depth=np.full((16,16),.3,np.float32);mask=np.ones((16,16),bool)
    k=np.array([[8.,0,7.5],[0,8.,7.5],[0,0,1.]])
    pose=np.eye(4);other=pose.copy();other[0,3]=.2
    assert exact_write_contract(a,depth,mask,k,pose)!=exact_write_contract(a,depth,mask,k,other)

def test_tiny_boundary_change_must_not_be_reused():
    rgb=np.zeros((16,16,3),np.uint8);depth=np.full((16,16),2.,np.float32);mask=np.ones((16,16),bool)
    k=np.array([[8.,0,7.5],[0,8.,7.5],[0,0,1.]])
    a=tile();b=tile();pose=np.eye(4);changed=pose.copy();changed[0,3]=1e-12
    assert exact_write_contract(a,depth,mask,k,pose)!=exact_write_contract(b,depth,mask,k,changed)
    for n in range(3):
        a.integrate(str(n),rgb,depth,mask,k,pose,source_hash='source')
        b.integrate(str(n),rgb,depth,mask,k,changed,source_hash='source')
    assert any(not np.array_equal(value,b.arrays()[name]) for name,value in a.arrays().items())



def test_inline_collection_matches_diagnostic_without_second_projection(monkeypatch):
    import graphAdapter.map_memory.geometry.core as core
    a=tile();rgb=np.zeros((16,16,3),np.uint8);depth=np.full((16,16),2.,np.float32);mask=np.ones((16,16),bool)
    k=np.array([[8.,0,7.5],[0,8.,7.5],[0,0,1.]]);pose=np.eye(4)
    expected=exact_write_contract(a,depth,mask,k,pose);calls=[];original=core.rigid_transform;contracts=[]
    def transform(*args):calls.append(1);return original(*args)
    monkeypatch.setattr(core,'rigid_transform',transform)
    a.integrate('frame',rgb,depth,mask,k,pose,source_hash='source',_write_collector=contracts.append)
    assert calls==[1] and contracts==[expected]


def test_service_contracts_survive_publication_reload(tmp_path):
    from test_continuous_graph import item,seeded_service
    from graphAdapter.map_memory.storage.store import EpisodeStore,load_episode
    p,a,m=item(1);store=EpisodeStore(tmp_path/'episode','unit',dataset='r2r')
    try:
        service=seeded_service(store,p,a);service.correction_options['record_geometry_write_contracts']=True
        service.ingest(p,**a,mapping_sample=m)
        contract=service.graph['geometry_results'][p.frame_uid]['write_contracts']
        assert contract['input_signature']==service.geometry.frames[p.frame_uid]
        assert len(contract['tiles'])==len(contract['candidates'])>0
        reader=store.open_reader()
        try:
            from graphAdapter.map_memory.storage.final_snapshot import plain
            assert plain(reader._graph['geometry_results'][p.frame_uid]['write_contracts'])==contract
            reader.verify()
        finally:reader.close()
    finally:store.close()


def test_target_only_certificate_checks_provenance_and_avoids_old_projection(monkeypatch):
    import copy
    import graphAdapter.map_memory.geometry.contribution_contract as contract
    from graphAdapter.map_memory.geometry.core import TSDFSubmapManager
    manager=TSDFSubmapManager([0.,0.,0.],voxel_size=.1,core_size=(1.,1.,1.),halo_cells=0,max_candidate_tiles=64,max_resident_tiles=64)
    rgb=np.zeros((8,8,3),np.uint8);depth=np.full((8,8),.3,np.float32);mask=np.ones((8,8),bool)
    k=np.array([[4.,0,3.5],[0,4.,3.5],[0,0,1.]]);pose=np.eye(4);pose[:3,3]=[.013,.027,.019]
    result=manager.integrate('frame',rgb,depth,mask,k,pose,source_hash='source',collect_write_contracts=True)
    saved=result['write_contracts'];changed=pose.copy();changed[0,3]+=1e-12
    calls=[];original=contract.rigid_transform
    def count(*args):calls.append(1);return original(*args)
    monkeypatch.setattr(contract,'rigid_transform',count)
    proof=contract.certify_frame_writes(manager,'frame',rgb,depth,mask,k,pose,changed,source_hash='source',record=saved)
    assert proof['certified'] and len(calls)==len(saved['candidates'])
    assert proof['source_signature']!=proof['target_signature']
    calls.clear()
    bad=contract.certify_frame_writes(manager,'other-frame',rgb,depth,mask,k,pose,changed,source_hash='source',record=saved)
    assert not bad['certified'] and calls==[]
    changed_rgb=rgb.copy();changed_rgb[0,0,0]=1
    bad=contract.certify_frame_writes(manager,'frame',changed_rgb,depth,mask,k,pose,changed,source_hash='source',record=saved)
    assert not bad['certified'] and calls==[]
    stale=copy.deepcopy(saved)
    for value in stale['tiles'].values():value['implementation_sha256']='0'*64
    assert not contract.certify_frame_writes(manager,'frame',rgb,depth,mask,k,pose,changed,source_hash='source',record=stale)['certified']
    far=pose.copy();far[0,3]+=1.
    assert not contract.certify_frame_writes(manager,'frame',rgb,depth,mask,k,pose,far,source_hash='source',record=saved)['certified']
