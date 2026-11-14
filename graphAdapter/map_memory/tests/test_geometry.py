"""CPU geometry component contracts; full G00-G14 and deployment remain separate."""
import importlib.util
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pytest
from scipy.spatial.transform import Rotation
from poseAdapter.coordinate.frames import OPTICAL_TO_FLU
from graphAdapter.map_memory.geometry.core import (
    A,S,Q,TSDFTile,TSDFPlannerBase,GeometryError,camera_branches,unproject_cv,
    object_points_world,transform_points,evidence_for_samples,checked_index,tile_key)
REF=Path(__file__).resolve().parents[4]/"docs/specs/graphAdapter-8d4e1845-6SDQEX/graphAdapter_execution/tools/reference_contracts.py"
def reference():
    import sys
    spec=importlib.util.spec_from_file_location("graph001_reference",REF)
    result=importlib.util.module_from_spec(spec);sys.modules[spec.name]=result;spec.loader.exec_module(result)
    return result
K=np.array([[4.,0.,3.5],[0.,4.,3.5],[0.,0.,1.]])
def tile(**kwargs):
    return TSDFTile("t0",np.array([[-1.,1.],[0.,6.],[-1.,1.]]),.25,np.eye(4),
                    base_position_L=np.zeros(3),near_m=0.,far_m=10.,**kwargs)
def image(depth=2.):
    return np.zeros((8,8,3),np.uint8),np.full((8,8),depth,np.float32),np.ones((8,8),bool)

@pytest.mark.parametrize("angles",[(0,0,0),(27,-19,43),(-43,81,-136)])
def test_G01_actual_boundary_noncentral_full_rotation_matches_reference(angles):
    ref=reference();k=np.array([[320.,0.,199.25],[0.,300.,111.5],[0.,0.,1.]])
    pose=np.eye(4);pose[:3,:3]=Rotation.from_euler("xyz",angles,degrees=True).as_matrix()
    pose[:3,3]=[-5.1,1.25,-7.3]
    uv=np.array([[23.,37.],[400.,211.],[199.25,111.5]])
    depths=np.array([2.,4.,.7])
    direct=transform_points(unproject_cv(uv,depths,k),pose)
    obj=object_points_world(uv,depths,k,256,pose)
    np.testing.assert_allclose(obj,direct,atol=1e-5,rtol=0)
    for pixel,depth,point in zip(uv,depths,obj):
        np.testing.assert_allclose(point,ref.object_convention(pixel,depth,k,256,pose),atol=1e-5,rtol=0)
    local=np.eye(4);local[:3,3]=[-8,3,-8]
    N=transform_points(direct,np.linalg.inv(local)@np.eye(4))
    N=transform_points(N,A)
    restored=transform_points(transform_points(N,np.linalg.inv(A)),local)
    np.testing.assert_allclose(restored,direct,atol=1e-5,rtol=0)

def test_G01_native_flu_is_converted_once_and_mount_height_remains_G_y():
    native=np.eye(4);native[:3,:3]=OPTICAL_TO_FLU;native[:3,3]=[0,0,1.25]
    branches=camera_branches(native,K,8)
    np.testing.assert_array_equal(branches["T_G_cv"][:3,:3],S[:3,:3])
    np.testing.assert_array_equal(branches["T_G_cv"][:3,3],[0,1.25,0])
    np.testing.assert_array_equal(branches["T_G_up"][:3,:3],np.eye(3))
    np.testing.assert_array_equal(K,branches["K_cv"])

def test_G02_evidence_far_legal_measurement_zero_nan_and_wall_behind():
    ref=reference()
    z=np.array([.5,1.9,2.,2.1,2.3,5.,-1.,np.nan])
    d=np.array([8.,2.,2.,2.,2.,8.,2.,2.])
    free,surface=evidence_for_samples(z,d,np.ones(len(z),bool),.1)
    expected=ref.evidence_labels(z,d,np.ones(len(z),bool),.1)
    np.testing.assert_array_equal(free,expected["free"])
    np.testing.assert_array_equal(surface,expected["surface"])
    assert free[0] and surface[2] and not free[4] and not surface[4] and not free[5]
    for depth in (0.,np.nan):
        t=tile();rgb,dep,mask=image(depth)
        t.integrate("e:f1",rgb,dep,mask,K,S,source_hash="same")
        assert not t.evidence()["observed"].any()
    t=tile();rgb,dep,mask=image(8)
    t.integrate("e:f1",rgb,dep,mask,K,S,source_hash="far")
    assert t.free_count.sum()>0 and t.surface_count.sum()==0

def test_G03_real_source_fusion_unchanged_by_rendering():
    a=tile(render_visualizations=False);b=tile(render_visualizations=True)
    rgb,dep,mask=image()
    for t in (a,b):t.integrate("e:f1",rgb,dep,mask,K,S,source_hash="source")
    for name,value in a.arrays().items():np.testing.assert_array_equal(value,b.arrays()[name])
    assert a.surface_count.sum()>0 and a.free_count.sum()>0
    assert not any(x in globals()for x in ("habitat_sim","Simulator","pathfinder"))

@pytest.mark.parametrize("point,expected",[
    ([-.01,0,0],None),([.999,0,0],None),([1.,0,0],None),([.9,0,0],(9,0,0)),([0,0,0],(0,0,0))])
def test_G04_halfopen_and_rounding_are_checked_without_clip(point,expected):
    assert checked_index(point,[0,0,0],[10,10,10],.1)==expected
    assert checked_index(point,[0,0,0],[10,10,10],.1)==reference().checked_voxel_index(point,[0,0,0],[10,10,10],.1)
    assert tile_key([-.001,-8.01,-3.01],[0,0,0],[8,8,3])==(-1,-2,-2)

def test_G04_source_cam2pix_rejects_bad_z_before_division_or_cast():
    pixels=TSDFPlannerBase.cam2pix(np.array([[0,0,0],[0,0,-1],[0,0,np.nan],[0,0,1],[1e308,0,1]]),K)
    np.testing.assert_array_equal(pixels[:3],np.full((3,2),-1))
    np.testing.assert_array_equal(pixels[3],[4,4])
    np.testing.assert_array_equal(pixels[4],[-1,-1])

def test_G06_duplicate_conflict_and_source_failure_retry_do_not_add_twice():
    t=tile();rgb,dep,mask=image();before={k:v.copy()for k,v in t.arrays().items()}
    original=t.volume.integrate
    def fail(*args,**kwargs):
        original(*args,**kwargs)
        raise OSError("fault after source fusion writes")
    with patch.object(t.volume,"integrate",side_effect=fail):
        with pytest.raises(OSError):t.integrate("e:f1",rgb,dep,mask,K,S,source_hash="h")
    for key,value in before.items():np.testing.assert_array_equal(t.arrays()[key],value)
    assert not t.frames
    assert t.integrate("e:f1",rgb,dep,mask,K,S,source_hash="h")
    after={k:v.copy()for k,v in t.arrays().items()}
    assert not t.integrate("e:f1",rgb,dep,mask,K,S,source_hash="h")
    for key,value in after.items():np.testing.assert_array_equal(t.arrays()[key],value)
    with pytest.raises(GeometryError,match="changed"):
        t.integrate("e:f1",rgb,dep+1,mask,K,S,source_hash="h")


from graphAdapter.map_memory.geometry.core import TSDFSubmapManager
class FixtureBacking:
    """CPU backing fixture only; deployment storage is exercised separately."""
    def __init__(self):self.items={};self.count=0;self.fail_at=None
    def save_tile(self,tile):
        self.count+=1
        if self.count==self.fail_at:raise OSError("injected tile write")
        meta,arrays=tile.export();key=str(self.count)
        self.items[key]=(meta,{k:v.copy()for k,v in arrays.items()})
        return key
    def load_tile(self,key):
        meta,arrays=self.items[key]
        return TSDFTile.restore(meta,arrays)

def test_G05_fixed_cores_match_single_source_volume_and_wall_tile_is_allocated():
    backing=FixtureBacking()
    manager=TSDFSubmapManager([0,0,0],voxel_size=.25,core_size=(2,2,2),
                             max_resident_tiles=2,max_total_tiles=64,backing=backing)
    rgb,dep,mask=image(2.13)
    k=np.array([[3.75,0,3.125],[0,3.75,3.375],[0,0,1.]])
    poses=[]
    for n,x in enumerate((-.5,.25)):
        pose=S.copy();pose[:3,3]=[x,0,-.5]
        result=manager.integrate("e:f"+str(n),rgb,dep,mask,k,pose,source_hash=str(n))
        assert result["has_evidence"];poses.append(pose)
    assert len(manager._cache)<=2
    assert any(key[1]==1 for key in manager.records)
    keys=np.asarray(list(manager.records))
    lower=keys.min(0)*2
    upper=(keys.max(0)+1)*2
    whole=TSDFTile("whole",np.stack((lower,upper),axis=1),.25,np.eye(4),
                   base_position_L=np.zeros(3),near_m=0,far_m=10)
    for n,pose in enumerate(poses):whole.integrate("e:f"+str(n),rgb,dep,mask,k,pose,source_hash=str(n))
    truth=whole.arrays()
    for key in manager.records:
        cells=manager.core_arrays(manager.identifier(key),snapshot_id="cpu:r1")["arrays"]
        offset=np.rint((np.asarray(key)*2-lower)/.25).astype(int)
        slices=tuple(slice(int(i),int(i+8))for i in offset)
        for name,value in cells.items():np.testing.assert_array_equal(value,truth[name][slices])

def test_G06_manager_storage_failure_rollback_then_retry_and_bounded_residency():
    backing=FixtureBacking()
    manager=TSDFSubmapManager([0,0,0],voxel_size=.25,core_size=(2,2,2),max_resident_tiles=2,backing=backing)
    rgb,dep,mask=image(2.13)
    manager.integrate("e:f1",rgb,dep,mask,K,S,source_hash="one")
    old=manager.records.copy();old_frames=manager.frames.copy()
    backing.fail_at=backing.count+2
    moved=S.copy();moved[:3,3]=[.5,0,0]
    with pytest.raises(OSError):
        manager.integrate("e:f2",rgb,dep,mask,K,moved,source_hash="two")
    assert manager.records==old and manager.frames==old_frames
    backing.fail_at=None
    manager.integrate("e:f2",rgb,dep,mask,K,moved,source_hash="two")
    assert len(manager.frames)==2 and len(manager._cache)<=2
    assert manager.integrate("e:f2",rgb,dep,mask,K,moved,source_hash="two")["duplicate"]

def test_G04_capacity_does_not_clip_or_delete_history():
    from graphAdapter.map_memory.geometry.core import CapacityError
    manager=TSDFSubmapManager([0,0,0],voxel_size=.25,core_size=(2,2,2),max_total_tiles=1)
    rgb,dep,mask=image(2.13)
    with pytest.raises(CapacityError):
        manager.integrate("e:f1",rgb,dep,mask,K,S,source_hash="one")
    assert not manager.records and not manager.frames
