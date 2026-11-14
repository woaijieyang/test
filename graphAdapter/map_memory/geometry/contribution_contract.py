"""Exact write-set diagnostic for the existing free/explore/evidence fusion.

Not a tolerance gate and not enabled as a replay shortcut. Equal contracts imply
identical writes from the same prior tile state for the existing unit-weight,
no-semantic, no-obstacle-visualization integration path.
"""
import hashlib,json
from pathlib import Path
IMPLEMENTATION_SHA256=hashlib.sha256(Path(__file__).with_name("core.py").read_bytes()+Path(__file__).read_bytes()).hexdigest()
import numpy as np
from .core import A,checked_intrinsic,checked_transform,valid_depth,rigid_transform,evidence_for_samples,array_hash,GeometryError

def exact_write_contract(tile,depth,mask,K,T_G_cv,*,explored_depth=1.7):
    if tile.volume.save_visualization:raise GeometryError('Obstacle visualization is outside the write contract')
    if not np.isfinite(explored_depth) or explored_depth<=0:raise GeometryError('Positive explore radius required')
    k=checked_intrinsic(K);t=checked_transform(T_G_cv)
    clean,good=valid_depth(depth,mask,tile.near_m,tile.far_m)
    local=A@np.linalg.inv(tile.T_G_L)@t
    points=rigid_transform(tile.volume.cam_pts_pre,np.linalg.inv(local))
    pixels=tile.volume.cam2pix(points,k);u,v=pixels[:,0],pixels[:,1];h,w=clean.shape;z=points[:,2]
    inside=(z>0)&np.isfinite(points).all(1)&(u>=0)&(u<w)&(v>=0)&(v<h)
    sampled=np.zeros(len(points),np.float32);valid=np.zeros(len(points),bool)
    sampled[inside]=clean[v[inside],u[inside]];valid[inside]=good[v[inside],u[inside]]
    free,surface=evidence_for_samples(z,sampled,valid,tile.voxel_size)
    source_inside=(u>=0)&(u<w)&(v>=0)&(v<h)&(z>0)&(z<5.)
    values=np.zeros(len(points));values[source_inside]=clean[v[source_inside],u[source_inside]]
    weight=(values>0)&(values-z>tile.voxel_size)
    narrow=values.copy()
    narrow[np.linalg.norm(tile.volume.cam_pts_pre[:,:2]-local[:2,3],axis=1)>=explored_depth]=0.
    explore=(narrow>0)&(narrow-z>tile.voxel_size)
    if not tile.record_surface_evidence:surface=np.zeros_like(surface)
    return contract_from_masks(tile,weight,explore,free,surface)

def contract_from_masks(tile,weight,explore,free,surface):
    writes={}
    for name,value in [('weight_and_positive_tsdf',weight),('explore_set_one',explore),('free_increment',free),('surface_increment',surface)]:
        packed=np.packbits(value,bitorder='little')
        writes[name]=dict(count=int(np.count_nonzero(value)),sha256=array_hash(packed))
    return dict(schema='source_fusion_exact_writes_v1',implementation_sha256=IMPLEMENTATION_SHA256,tile_id=tile.tile_id,voxel_count=len(tile.volume.cam_pts_pre),
        lattice_sha256=array_hash(tile.volume.cam_pts_pre),indices_sha256=array_hash(tile.volume.vox_coords),
        writes=writes,obs_weight=1.,tsdf_observation_value=1.)


def certify_frame_writes(manager,frame_uid,rgb,depth,mask,K,old_pose,target_pose,*,source_hash,record,explored_depth=1.7):
    """Validate immutable old inputs, then project ONLY the target pose.

    This produces a certificate; it does not mutate geometry or bypass semantic
    correction. Missing/old/incompatible cache entries fail closed.
    """
    k=checked_intrinsic(K);old=checked_transform(old_pose);target=checked_transform(target_pose)
    def signature(pose):
        return hashlib.sha256(('|'.join([source_hash,*[array_hash(x) for x in
            (rgb,depth,mask,k,pose,np.asarray([explored_depth]))]])).encode()).hexdigest()
    old_signature=signature(old)
    if not isinstance(record,dict) or record.get('input_signature')!=old_signature or manager.frames.get(frame_uid)!=old_signature:
        return dict(certified=False,reason='missing_or_mismatched_source_contribution',checked_tiles=0)
    keys=manager._candidates(depth,mask,k,target);ids=[manager.identifier(key) for key in keys]
    if record.get('candidates')!=ids or set(record.get('tiles',{}))!=set(ids):
        return dict(certified=False,reason='candidate_set_changed',checked_tiles=0)
    contracts={}
    for key,name in zip(keys,ids):
        previous=record['tiles'][name]
        if previous.get('implementation_sha256')!=IMPLEMENTATION_SHA256:
            return dict(certified=False,reason='implementation_changed',checked_tiles=len(contracts))
        tile=manager._new_tile(key)
        current=exact_write_contract(tile,depth,mask,k,target,explored_depth=explored_depth)
        contracts[name]=current
        if current!=previous:
            return dict(certified=False,reason='write_set_changed',tile_id=name,checked_tiles=len(contracts))
    return dict(certified=True,reason='all_source_writes_identical',checked_tiles=len(contracts),
        source_signature=old_signature,target_signature=signature(target),
        target_contract=dict(input_signature=signature(target),candidates=ids,tiles=contracts))
