# Modified by 2024 Allen Ren, Princeton University
# Copyright (c) 2018 Andy Zeng
# Source: https://github.com/andyzeng/tsdf-fusion-python/blob/master/fusion.py
# BSD 2-Clause License
# Copyright (c) 2019, Princeton University
# All rights reserved.

# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:

# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.

# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.

# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.


# Source5770e8cc. Import isolation, safe projection/raw indices, explicit evidence.
import numpy as np
from numba import njit,prange
from functools import lru_cache

def points_in_circle(center_x, center_y, radius, grid_shape):
    x, y = np.meshgrid(
        np.arange(grid_shape[0]), np.arange(grid_shape[1]), indexing="ij"
    )  # use matrix indexing instead of cartesian
    distance_matrix = np.sqrt((x - center_x) ** 2 + (y - center_y) ** 2)
    points_within_circle = np.where(distance_matrix <= radius)
    return list(zip(points_within_circle[0], points_within_circle[1]))

def rigid_transform(xyz, transform):
    """Applies a rigid transform to an (N, 3) pointcloud."""
    xyz_h = np.hstack([xyz, np.ones((len(xyz), 1), dtype=np.float32)])
    xyz_t_h = np.dot(transform, xyz_h.T).T
    return xyz_t_h[:, :3]

def pos_habitat_to_normal(pts):
    # -90 deg around x-axis
    return np.dot(pts, np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]]))

class TSDFPlannerBase:
    def __init__(
        self,
        vol_bnds,
        voxel_size,
        floor_height,
        floor_height_offset=0,
        pts_init=None,
        init_clearance=0,
        save_visualization=False,
        *,
        _lattice=None,
    ):
        """Constructor.
        Args:
          vol_bnds (ndarray): An ndarray of shape (3, 2). Specifies the
            xyz bounds (min/max) in meters.
          voxel_size (float): The volume discretization in meters.
        """
        vol_bnds = np.asarray(vol_bnds)
        assert vol_bnds.shape == (3, 2), "[!] `vol_bnds` should be of shape (3, 2)."
        assert (vol_bnds[:, 0] < vol_bnds[:, 1]).all()

        # Define voxel volume parameters
        self._vol_bnds = vol_bnds
        self._voxel_size = float(voxel_size)

        # Adjust volume bounds and ensure C-order contiguous
        self._vol_dim = (
            np.ceil((self._vol_bnds[:, 1] - self._vol_bnds[:, 0]) / self._voxel_size)
            .copy(order="C")
            .astype(int)
        )
        self._vol_bnds[:, 1] = self._vol_bnds[:, 0] + self._vol_dim * self._voxel_size
        self._vol_origin = self._vol_bnds[:, 0].copy(order="C").astype(np.float32)

        # Initialize pointers to voxel volume in CPU memory
        # Assume all unobserved regions are occupied
        self._tsdf_vol_cpu = -np.ones(self._vol_dim).astype(np.float32)
        # for computing the cumulative moving average of observations per voxel
        self._weight_vol_cpu = np.zeros(self._vol_dim).astype(np.float32)

        self.save_visualization = save_visualization
        if save_visualization:
            # Initialize obstacle volume
            self._obstacle_vol_cpu = np.zeros(self._vol_dim).astype(bool)
        else:
            self._obstacle_vol_cpu = None

        # Explored or not
        self._explore_vol_cpu = np.zeros(self._vol_dim).astype(np.float32)

        if _lattice is None:
            # Get voxel grid coordinates
            xv, yv, zv = np.meshgrid(
                range(self._vol_dim[0]),
                range(self._vol_dim[1]),
                range(self._vol_dim[2]),
                indexing="ij",
            )
            self.vox_coords = (
                np.concatenate(
                    [xv.reshape(1, -1), yv.reshape(1, -1), zv.reshape(1, -1)], axis=0
                )
                .astype(int)
                .T
            )

            # pre-compute
            self.cam_pts_pre = TSDFPlannerBase.vox2world(
                self._vol_origin, self.vox_coords, self._voxel_size
            )

        else:
            self.vox_coords, self.cam_pts_pre = _lattice

        self.floor_height = floor_height

        # Find the minimum height voxel
        self.min_height_voxel = int(floor_height_offset / self._voxel_size)

        # For masking the area around initial pose to be unoccupied
        coords_init = self.habitat2voxel(pts_init)
        self.init_points = points_in_circle(
            coords_init[0],
            coords_init[1],
            int(init_clearance / self._voxel_size),
            self._vol_dim[:2],
        )
    @staticmethod
    @njit(parallel=True)
    def vox2world(vol_origin, vox_coords, vox_size):
        """Convert voxel grid coordinates to world coordinates."""
        vol_origin = vol_origin.astype(np.float32)
        vox_coords = vox_coords.astype(np.float32)
        cam_pts = np.empty_like(vox_coords, dtype=np.float32)
        for i in prange(vox_coords.shape[0]):
            for j in range(3):
                cam_pts[i, j] = vol_origin[j] + (vox_size * vox_coords[i, j])
        return cam_pts
    @staticmethod
    @njit(parallel=True)
    def cam2pix(cam_pts,intr):
        intr=intr.astype(np.float32)
        fx,fy=intr[0,0],intr[1,1];cx,cy=intr[0,2],intr[1,2]
        pixels=np.full((cam_pts.shape[0],2),-1,np.int64)
        for i in prange(cam_pts.shape[0]):
            z=cam_pts[i,2]
            if not np.isfinite(z) or z<=0:continue
            u=cam_pts[i,0]*fx/z+cx;v=cam_pts[i,1]*fy/z+cy
            if np.isfinite(u) and np.isfinite(v) and abs(u)<1e18 and abs(v)<1e18:
                pixels[i,0]=int(np.round(u));pixels[i,1]=int(np.round(v))
        return pixels
    def normal2voxel(self, pts):
        pts = pts - self._vol_origin
        coords = np.round(pts / self._voxel_size).astype(int)
        return coords
    @staticmethod
    @njit(parallel=True)
    def integrate_tsdf(tsdf_vol, dist, w_old, obs_weight):
        """Integrate the TSDF volume."""
        tsdf_vol_int = np.empty_like(tsdf_vol, dtype=np.float32)
        w_new = np.empty_like(w_old, dtype=np.float32)
        for i in prange(len(tsdf_vol)):
            w_new[i] = w_old[i] + obs_weight
            tsdf_vol_int[i] = (w_old[i] * tsdf_vol[i] + obs_weight * dist[i]) / w_new[i]
        return tsdf_vol_int, w_new
    def integrate(
        self,
        color_im,
        depth_im,
        cam_intr,
        cam_pose,
        sem_im=None,
        w_new=None,
        obs_weight=1.0,
        margin_h=240,  # from top
        margin_w=120,  # each side
        explored_depth=1.5,
        *,
        _projection=None,
        _write_collector=None,
    ):
        """Integrate an RGB-D frame into the TSDF volume.
        Args:
          color_im (ndarray): An RGB image of shape (H, W, 3).
          depth_im (ndarray): A depth image of shape (H, W).
          cam_intr (ndarray): The camera intrinsics matrix of shape (3, 3).
          cam_pose (ndarray): The camera pose (i.e. extrinsics) of shape (4, 4).
          sem_im (ndarray): An semantic image of shape (H, W).
          obs_weight (float): The weight to assign for the current observation. A higher
            value
          margin_h (int): The margin from the top of the image to exclude when integrating explored
          margin_w (int): The margin from the sides of the image to exclude when integrating explored
        """
        im_h, im_w = depth_im.shape
        max_dist = 5.0

        # Convert voxel grid coordinates to pixel coordinates
        if _projection is None:
            cam_pts = rigid_transform(self.cam_pts_pre, np.linalg.inv(cam_pose))
            pix = TSDFPlannerBase.cam2pix(cam_pts, cam_intr)
        else:
            # Internal, call-local projection from TSDFTile. No cross-frame cache.
            grid, intrinsic, pose, cam_pts, pix = _projection
            if (grid is not self.cam_pts_pre
                    or not np.array_equal(intrinsic, cam_intr)
                    or not np.array_equal(pose, cam_pose)):
                raise ValueError("Projection belongs to another tile or camera")
            if cam_pts.shape != self.cam_pts_pre.shape or pix.shape != (len(cam_pts), 2):
                raise ValueError("Projection dimensions differ from the tile")
        pix_z = cam_pts[:, 2]
        pix_x, pix_y = pix[:, 0], pix[:, 1]

        cur_pose_xy = cam_pose[:2, 3]

        # Eliminate pixels outside view frustum
        valid_pix = (
            (pix_x >= 0)
            & (pix_x < im_w)
            & (pix_y >= 0)
            & (pix_y < im_h)
            & (pix_z > 0)
            & (pix_z < max_dist)
        )
        depth_val = np.zeros(pix_x.shape)
        depth_val[valid_pix] = depth_im[pix_y[valid_pix], pix_x[valid_pix]]

        # narrow view
        depth_val_narrow = np.zeros(pix_x.shape)
        depth_val_narrow[valid_pix] = depth_im[pix_y[valid_pix], pix_x[valid_pix]]
        # depth_val_narrow[depth_val_narrow >= explored_depth] = 0.0
        depth_val_narrow[
            np.linalg.norm(self.cam_pts_pre[:, :2] - cur_pose_xy, axis=1)
            >= explored_depth
        ] = 0.0

        # Integrate TSDF
        depth_diff = depth_val - pix_z
        depth_margin = 1 * self._voxel_size
        valid_pts = np.logical_and(depth_val > 0, depth_diff > depth_margin)
        dist = np.where(depth_diff > depth_margin, 1.0, -1.0)
        valid_vox_x = self.vox_coords[valid_pts, 0]
        valid_vox_y = self.vox_coords[valid_pts, 1]
        valid_vox_z = self.vox_coords[valid_pts, 2]
        w_old = self._weight_vol_cpu[valid_vox_x, valid_vox_y, valid_vox_z]

        if self.save_visualization:
            # Mark obstacle
            obstacle_pts = (
                (depth_diff < 0)
                & (depth_diff >= -0.2)
                & (pix_x >= 0)
                & (pix_x < im_w)
                & (pix_y >= 0)
                & (pix_y < im_h)
                & (pix_z > 0)
                & (pix_z < max_dist)
            )
            obstacle_vox_x = self.vox_coords[obstacle_pts, 0]
            obstacle_vox_y = self.vox_coords[obstacle_pts, 1]
            obstacle_vox_z = self.vox_coords[obstacle_pts, 2]
            self._obstacle_vol_cpu[obstacle_vox_x, obstacle_vox_y, obstacle_vox_z] = (
                True
            )

        depth_diff_narrow = depth_val_narrow - pix_z
        valid_pts_narrow = np.logical_and(
            depth_val_narrow > 0, depth_diff_narrow > depth_margin
        )
        valid_vox_x_narrow = self.vox_coords[valid_pts_narrow, 0]
        valid_vox_y_narrow = self.vox_coords[valid_pts_narrow, 1]
        valid_vox_z_narrow = self.vox_coords[valid_pts_narrow, 2]
        if _write_collector is not None:_write_collector(valid_pts,valid_pts_narrow)
        if w_new is None:
            tsdf_vals = self._tsdf_vol_cpu[valid_vox_x, valid_vox_y, valid_vox_z]
            valid_dist = dist[valid_pts]
            tsdf_vol_new, w_new = TSDFPlannerBase.integrate_tsdf(
                tsdf_vals, valid_dist, w_old, obs_weight
            )
            self._weight_vol_cpu[valid_vox_x, valid_vox_y, valid_vox_z] = w_new
            self._tsdf_vol_cpu[valid_vox_x, valid_vox_y, valid_vox_z] = tsdf_vol_new

            # Mark explored
            self._explore_vol_cpu[
                valid_vox_x_narrow, valid_vox_y_narrow, valid_vox_z_narrow
            ] = 1

        return w_new
    def habitat2voxel(self, pts):
        pts_normal = pos_habitat_to_normal(pts)
        pts_voxel = self.normal2voxel(pts_normal)
        return pts_voxel


import hashlib
from poseAdapter.coordinate.frames import FLU_TO_HARNESS
from poseAdapter.coordinate.transforms import checked_transform

Q=np.eye(4);Q[:3,:3]=FLU_TO_HARNESS
S=np.diag([1.,-1.,-1.,1.])
A=np.array([[1.,0.,0.,0.],[0.,0.,-1.,0.],[0.,1.,0.,0.],[0.,0.,0.,1.]])
for matrix in (Q,S,A):matrix.setflags(write=False)

class GeometryError(ValueError):
    pass

class CapacityError(RuntimeError):
    pass

def checked_intrinsic(value):
    k=np.asarray(value,np.float64)
    if (k.shape!=(3,3) or not np.isfinite(k).all() or min(k[0,0],k[1,1])<=0
        or not np.allclose(k[2],[0,0,1],atol=1e-12)
        or abs(k[0,1])>1e-12 or abs(k[1,0])>1e-12):
        raise GeometryError("Finite zero-skew optical pinhole intrinsics required")
    return k.copy()

def transform_points(points,pose):
    points=np.asarray(points,np.float64);t=checked_transform(pose)
    if points.shape[-1]!=3 or not np.isfinite(points).all():
        raise GeometryError("Finite 3D points required")
    return points@t[:3,:3].T+t[:3,3]

def camera_branches(T_M_cv,K_cv,height):
    if type(height)is not int or height<=0:raise GeometryError("Positive RGB height required")
    t=Q@checked_transform(T_M_cv);k=checked_intrinsic(K_cv);up=k.copy()
    up[1,2]=height-1-k[1,2]
    return dict(T_G_cv=t,T_G_up=t@S,K_cv=k,K_up=up)

def unproject_cv(uv,depth,intrinsic):
    k=checked_intrinsic(intrinsic);uv=np.asarray(uv,np.float64);d=np.asarray(depth,np.float64)
    if uv.shape[-1]!=2 or not np.isfinite(uv).all() or not np.isfinite(d).all() or np.any(d<=0):
        raise GeometryError("Finite pixels and positive metric z-depth required")
    u,v=uv[...,0],uv[...,1]
    return np.stack(((u-k[0,2])*d/k[0,0],(v-k[1,2])*d/k[1,1],np.broadcast_to(d,u.shape)),axis=-1)

def object_points_world(uv,depth,intrinsic,height,T_G_cv):
    k=checked_intrinsic(intrinsic);up=k.copy();up[1,2]=height-1-up[1,2]
    uv=np.asarray(uv,np.float64);z=np.asarray(depth,np.float64)
    x=(uv[...,0]-up[0,2])*z/up[0,0];y=(height-1-uv[...,1]-up[1,2])*z/up[1,1]
    return transform_points(np.stack((x,y,-np.broadcast_to(z,x.shape)),axis=-1),checked_transform(T_G_cv)@S)

def valid_depth(depth,mask,near,far):
    depth=np.asarray(depth);mask=np.asarray(mask)
    if (depth.ndim!=2 or depth.dtype!=np.float32 or mask.shape!=depth.shape or mask.dtype!=np.bool_
        or not np.isfinite([near,far]).all() or near<0 or far<=near):
        raise GeometryError("Aligned float32 metric z-depth and bool validity required")
    good=mask&np.isfinite(depth)&(depth>near)&(depth<=far)
    return np.where(good,depth,0).astype(np.float32),good

def evidence_for_samples(voxel_z,depth,valid,voxel_size,max_voxel_depth=5.):
    z,d=np.broadcast_arrays(np.asarray(voxel_z,np.float64),np.asarray(depth,np.float64))
    ok=np.broadcast_to(valid,z.shape)&np.isfinite(z)&np.isfinite(d)&(d>0)&(z>0)&(z<max_voxel_depth)
    return ok&(d-z>voxel_size),ok&(np.abs(d-z)<=voxel_size/2)

def checked_index(point,origin,dims,voxel_size):
    p,o=np.asarray(point,np.float64),np.asarray(origin,np.float64);n=np.asarray(dims)
    if (p.shape!=(3,) or o.shape!=(3,) or n.shape!=(3,) or not np.isfinite(np.r_[p,o]).all()
        or n.dtype.kind not in "iu" or np.any(n<=0) or not np.isfinite(voxel_size) or voxel_size<=0):
        raise GeometryError("Invalid voxel address")
    continuous=(p-o)/voxel_size
    if np.any(continuous<0) or np.any(continuous>=n):return None
    raw=np.rint(continuous).astype(np.int64)
    return None if np.any(raw<0) or np.any(raw>=n) else tuple(int(x)for x in raw)

def tile_key(point_N,origin_N,core_size):
    p,o,s=[np.asarray(x,np.float64)for x in (point_N,origin_N,core_size)]
    if any(x.shape!=(3,)for x in (p,o,s)) or not np.isfinite(np.r_[p,o,s]).all() or np.any(s<=0):
        raise GeometryError("Invalid tile coordinates")
    return tuple(np.floor((p-o)/s).astype(np.int64).tolist())

def array_hash(array):
    a=np.ascontiguousarray(array)
    return hashlib.sha256(str(a.dtype).encode()+str(a.shape).encode()+a.tobytes()).hexdigest()

@lru_cache(maxsize=1)
def _tile_lattice(bounds, voxel_size):
    """One immutable local lattice shared by equal tile shapes, independent of poses."""
    bounds = np.asarray(bounds, dtype=np.float64).reshape(3, 2)
    dimensions = np.ceil((bounds[:, 1] - bounds[:, 0]) / voxel_size).astype(int)
    axes = np.meshgrid(*(range(n) for n in dimensions), indexing="ij")
    coordinates = np.concatenate([axis.reshape(1, -1) for axis in axes], axis=0).astype(int).T
    points = bounds[:, 0] + coordinates.astype(np.float64) * voxel_size
    coordinates.setflags(write=False)
    points.setflags(write=False)
    return coordinates, points


class TSDFTile:
    """Source free/explore fusion plus separate observation evidence, no planner."""
    def __init__(self,tile_id,bounds_Nlocal,voxel_size,T_G_L,*,base_position_L,near_m,far_m,
                 record_surface_evidence=True,render_visualizations=False):
        self.tile_id=str(tile_id)
        if not self.tile_id or "/"in self.tile_id:raise GeometryError("Safe tile identity required")
        b=np.asarray(bounds_Nlocal,np.float64)
        if b.shape!=(3,2) or not np.isfinite(b).all() or np.any(b[:,1]<=b[:,0]):
            raise GeometryError("Finite tile bounds required")
        self.T_G_L=checked_transform(T_G_L).copy();self.voxel_size=float(voxel_size)
        if not np.allclose(self.T_G_L[:3,:3],np.eye(3),atol=1e-12,rtol=0):raise GeometryError("Tile L axes must remain parallel to G")
        if not np.isfinite(self.voxel_size) or self.voxel_size<=0:raise GeometryError("Positive voxel size required")
        self.near_m=float(near_m);self.far_m=float(far_m)
        if not np.isfinite([self.near_m,self.far_m]).all() or not 0<=self.near_m<self.far_m:
            raise GeometryError("Finite sensor range required")
        self.record_surface_evidence=bool(record_surface_evidence)
        self.render_visualizations=bool(render_visualizations)
        dimensions=np.ceil((b[:,1]-b[:,0])/self.voxel_size)
        if not np.isfinite(dimensions).all() or np.prod(dimensions)>2_000_000:
            raise CapacityError("Single tile voxel allocation budget exceeded")
        lattice = _tile_lattice(tuple(b.ravel()), self.voxel_size)
        self.volume=TSDFPlannerBase(b.copy(),self.voxel_size,0.,
            pts_init=np.asarray(base_position_L,np.float64),init_clearance=0.,save_visualization=False,
            _lattice=lattice)
        self.free_count=np.zeros(tuple(self.volume._vol_dim),np.uint32)
        self.surface_count=np.zeros_like(self.free_count);self.frames={}

    def contains_world_point(self,point_G):
        local=transform_points(np.asarray(point_G)[None],np.linalg.inv(self.T_G_L))
        n=transform_points(local,A)[0]
        b=(np.stack((np.zeros(3),np.asarray(self.core_cells)*self.voxel_size),axis=1)
           if hasattr(self,"core_cells") else self.volume._vol_bnds)
        return bool(np.all(n>=b[:,0]) and np.all(n<b[:,1]))

    def integrate(self,frame_uid,rgb,depth,mask,K_cv,T_G_cv,*,source_hash,explored_depth=1.7,_write_collector=None):
        if not np.isfinite(explored_depth) or explored_depth<=0:raise GeometryError("Positive finite explore radius required")
        rgb=np.asarray(rgb);k=checked_intrinsic(K_cv);t=checked_transform(T_G_cv)
        clean,good=valid_depth(depth,mask,self.near_m,self.far_m)
        if rgb.shape!=clean.shape+(3,) or rgb.dtype!=np.uint8:
            raise GeometryError("Same-frame uint8 RGB and aligned depth required")
        if not isinstance(frame_uid,str) or not frame_uid or not isinstance(source_hash,str) or not source_hash:
            raise GeometryError("Frame and source identity required")
        signature=hashlib.sha256(("|".join([source_hash,*[array_hash(x)for x in
            (rgb,depth,mask,k,t,self.T_G_L,np.asarray([explored_depth,self.near_m,self.far_m,self.voxel_size,self.record_surface_evidence]))]])).encode()).hexdigest()
        if frame_uid in self.frames:
            if self.frames[frame_uid]!=signature:raise GeometryError("Immutable frame contribution changed")
            return False
        local=A@np.linalg.inv(self.T_G_L)@t
        points=rigid_transform(self.volume.cam_pts_pre,np.linalg.inv(local))
        pixels=self.volume.cam2pix(points,k);u,v=pixels[:,0],pixels[:,1];h,w=clean.shape
        inside=(points[:,2]>0)&np.isfinite(points).all(1)&(u>=0)&(u<w)&(v>=0)&(v<h)
        sampled=np.zeros(len(points),np.float32);valid=np.zeros(len(points),bool)
        sampled[inside]=clean[v[inside],u[inside]];valid[inside]=good[v[inside],u[inside]]
        free,surface=evidence_for_samples(points[:,2],sampled,valid,self.voxel_size)
        names=("_tsdf_vol_cpu","_weight_vol_cpu","_explore_vol_cpu")
        before=[getattr(self.volume,x)for x in names];old_free=self.free_count;old_surface=self.surface_count
        try:
            for name,array in zip(names,before):setattr(self.volume,name,array.copy())
            self.free_count=old_free.copy();self.surface_count=old_surface.copy()
            def collect(weight,explore):
                from .contribution_contract import contract_from_masks
                _write_collector(contract_from_masks(self,weight,explore,free,
                    surface if self.record_surface_evidence else np.zeros_like(surface)))
            self.volume.integrate(rgb,clean,k,local,obs_weight=1.,explored_depth=explored_depth,
                                  _projection=(self.volume.cam_pts_pre,k,local,points,pixels),
                                  _write_collector=collect if _write_collector is not None else None)
            self.free_count.ravel()[free]+=1
            if self.record_surface_evidence:self.surface_count.ravel()[surface]+=1
        except BaseException:
            for name,array in zip(names,before):setattr(self.volume,name,array)
            self.free_count=old_free;self.surface_count=old_surface
            raise
        self.frames[frame_uid]=signature
        return True

    def fork(self):
        import copy
        result=copy.copy(self)
        result.volume=copy.copy(self.volume)
        result.frames=self.frames.copy()
        return result

    def export(self):
        meta=dict(tile_id=self.tile_id,bounds=self.volume._vol_bnds.tolist(),
            voxel_size=self.voxel_size,T_G_L=self.T_G_L.tolist(),near_m=self.near_m,far_m=self.far_m,
            record_surface_evidence=self.record_surface_evidence,frames=self.frames.copy(),
            core_cells=[int(x)for x in getattr(self,"core_cells",self.volume._vol_dim)],
            halo_cells=int(getattr(self,"halo_cells",0)))
        return meta,self.arrays()

    @classmethod
    def restore(cls,meta,arrays):
        tile=cls(meta["tile_id"],meta["bounds"],meta["voxel_size"],meta["T_G_L"],
            base_position_L=np.zeros(3),near_m=meta["near_m"],far_m=meta["far_m"],
            record_surface_evidence=meta["record_surface_evidence"])
        expected={"tsdf":np.float32,"weight":np.float32,"explore":np.float32,
                  "free_count":np.uint32,"surface_count":np.uint32}
        if set(arrays)!=set(expected):raise GeometryError("Tile array schema mismatch")
        shape=tuple(tile.volume._vol_dim)
        for name,dtype in expected.items():
            a=np.asarray(arrays[name])
            if a.shape!=shape or a.dtype!=dtype or not np.isfinite(a).all():
                raise GeometryError("Tile array shape/dtype/finite mismatch: "+name)
        tile.volume._tsdf_vol_cpu=np.array(arrays["tsdf"],copy=True)
        tile.volume._weight_vol_cpu=np.array(arrays["weight"],copy=True)
        tile.volume._explore_vol_cpu=np.array(arrays["explore"],copy=True)
        tile.free_count=np.array(arrays["free_count"],copy=True)
        tile.surface_count=np.array(arrays["surface_count"],copy=True)
        tile.frames=dict(meta["frames"]);tile.core_cells=tuple(meta.get("core_cells",shape))
        tile.halo_cells=int(meta.get("halo_cells",0))
        return tile

    def arrays(self):
        items=dict(tsdf=self.volume._tsdf_vol_cpu,weight=self.volume._weight_vol_cpu,
            explore=self.volume._explore_vol_cpu,free_count=self.free_count,surface_count=self.surface_count)
        result={}
        for name,array in items.items():
            result[name]=array.view();result[name].setflags(write=False)
        return result

    def evidence(self):
        free=self.free_count>0;surface=self.surface_count>0
        return dict(free_evidence=free,surface_evidence=surface,observed=free|surface,
                    unknown=~(free|surface),conflict=free&surface,free=free&~surface)


class TSDFSubmapManager:
    """Aligned fixed cores, transient halos, bounded residency, immutable backing records.

    backing.save_tile(tile)->opaque record and backing.load_tile(record)->TSDFTile
    are storage interfaces. Allocation never uses a simulator or scene bounds.
    """
    def __init__(self,origin_G,*,voxel_size=.1,core_size=(8.,8.,3.),halo_cells=1,
                 near_m=0.,far_m=10.,max_resident_tiles=16,max_total_tiles=512,
                 max_candidate_tiles=64,backing=None):
        from collections import OrderedDict
        self.origin_G=np.asarray(origin_G,np.float64).copy()
        self.core_size=np.asarray(core_size,np.float64)
        if self.origin_G.shape!=(3,) or self.core_size.shape!=(3,) or not np.isfinite(np.r_[self.origin_G,self.core_size]).all():
            raise GeometryError("Finite explicit estimated grid origin/core sizes required")
        self.voxel_size=float(voxel_size)
        if self.voxel_size<=0 or not np.isfinite(self.voxel_size) or np.any(self.core_size<=0):
            raise GeometryError("Positive voxel/core sizes required")
        cells=self.core_size/self.voxel_size
        if not np.allclose(cells,np.rint(cells),atol=1e-8,rtol=0):
            raise GeometryError("Core must be an integer voxel lattice")
        self.core_cells=np.rint(cells).astype(np.int64)
        if type(halo_cells)is not int or halo_cells<0:raise GeometryError("Nonnegative integer halo required")
        self.halo_cells=halo_cells
        for value in (max_resident_tiles,max_total_tiles,max_candidate_tiles):
            if type(value)is not int or value<1:raise GeometryError("Positive integer capacity required")
        self.max_resident_tiles=max_resident_tiles;self.max_total_tiles=max_total_tiles
        self.max_candidate_tiles=max_candidate_tiles
        self.near_m=float(near_m);self.far_m=float(far_m);self.backing=backing
        self.records={};self.frames={};self._cache=OrderedDict()

    @staticmethod
    def identifier(key):
        return "tile_"+"_".join(str(int(x))for x in key)

    @staticmethod
    def parse_identifier(value):
        try:
            parts=value.removeprefix("tile_").split("_")
            key=tuple(int(x)for x in parts)
        except (ValueError,AttributeError):raise GeometryError("Invalid tile identity")
        if len(key)!=3 or value!=TSDFSubmapManager.identifier(key):raise GeometryError("Invalid tile identity")
        return key

    def fork(self):
        import copy
        from collections import OrderedDict
        result=copy.copy(self);result.records=self.records.copy();result.frames=self.frames.copy()
        result._cache=OrderedDict(self._cache)
        return result

    def _new_tile(self,key):
        offset=np.asarray(key,np.float64)*self.core_size
        transform=np.eye(4);transform[:3,3]=self.origin_G+A[:3,:3].T@offset
        halo=self.halo_cells*self.voxel_size
        bounds=np.stack((-np.full(3,halo),self.core_size+halo),axis=1)
        tile=TSDFTile(self.identifier(key),bounds,self.voxel_size,transform,
            base_position_L=np.zeros(3),near_m=self.near_m,far_m=self.far_m)
        tile.core_cells=tuple(int(x)for x in self.core_cells);tile.halo_cells=self.halo_cells
        return tile

    def _load(self,key):
        if key in self._cache:
            tile=self._cache.pop(key);self._cache[key]=tile
            return tile
        if key not in self.records:return self._new_tile(key)
        if self.backing is None:raise CapacityError("Evicted tile has no persistent backing")
        tile=self.backing.load_tile(self.records[key])
        if tile.tile_id!=self.identifier(key):raise GeometryError("Backing tile identity mismatch")
        return tile

    def _cache_tile(self,key,tile):
        self._cache.pop(key,None);self._cache[key]=tile
        while len(self._cache)>self.max_resident_tiles:
            if self.backing is None:raise CapacityError("Residency exhausted without durable tile backing")
            self._cache.popitem(last=False)

    def locate(self,point_G):
        """Canonical owner of the rounded sample, never a clipped edge address."""
        p=np.asarray(point_G,np.float64)
        if p.shape!=(3,) or not np.isfinite(p).all():raise GeometryError("Finite world query required")
        n=A[:3,:3]@(p-self.origin_G)
        continuous=n/self.voxel_size
        if np.any(np.abs(continuous)>2**52):raise CapacityError("Voxel index exceeds exact integer precision budget")
        # Check actual unrounded half-open core before routing a rounded halo sample.
        original=tile_key(n,np.zeros(3),self.core_size)
        lower=np.asarray(original)*self.core_size
        if not (np.all(n>=lower) and np.all(n<lower+self.core_size)):
            raise GeometryError("Half-open tile ownership check failed")
        global_index=np.rint(continuous).astype(np.int64)
        owner=tuple(np.floor_divide(global_index,self.core_cells).tolist())
        index=tuple((global_index-np.asarray(owner)*self.core_cells).tolist())
        if any(i<0 or i>=d for i,d in zip(index,self.core_cells)):raise GeometryError("Unclipped owner index invalid")
        return self.identifier(owner),index

    def _candidates(self,depth,valid,K,T_G_cv):
        import itertools
        clean,good=valid_depth(depth,valid,self.near_m,self.far_m)
        v,u=np.nonzero(good)
        if not len(u):return []
        # cam2pix uses nearest pixels: their support includes half-pixel rays,
        # and the conservative surface band extends beyond the measured centre.
        # The rectangle is only a candidate envelope; actual valid rays/evidence
        # decide whether a tile is retained.
        corners=np.array([[u.min()-.5,v.min()-.5],[u.min()-.5,v.max()+.5],
                          [u.max()+.5,v.min()-.5],[u.max()+.5,v.max()+.5]])
        z=min(float(clean[good].max())+self.voxel_size/2,5.)
        rays=unproject_cv(corners,np.full(4,z),K)
        points=transform_points(rays,T_G_cv)
        points=np.vstack((points,np.asarray(T_G_cv)[:3,3]))
        n=(points-self.origin_G)@A[:3,:3].T
        if not np.isfinite(n).all() or np.any(np.abs(n/self.voxel_size)>2**52):raise CapacityError("Frame exceeds exact lattice precision budget")
        low=n.min(0)-self.voxel_size;high=n.max(0)+self.voxel_size
        first=tile_key(low,np.zeros(3),self.core_size);last=tile_key(high,np.zeros(3),self.core_size)
        count=int(np.prod(np.asarray(last,dtype=object)-np.asarray(first,dtype=object)+1))
        if count>self.max_candidate_tiles:raise CapacityError("Frame frustum candidate tile budget exceeded")
        return list(itertools.product(*(range(a,b+1)for a,b in zip(first,last))))

    def _core_slice(self):
        h=self.halo_cells
        return tuple(slice(h,h+int(n))for n in self.core_cells)

    def integrate(self,frame_uid,rgb,depth,mask,K,T_G_cv,*,source_hash,explored_depth=1.7,collect_write_contracts=False):
        k=checked_intrinsic(K);t=checked_transform(T_G_cv)
        signature=hashlib.sha256(("|".join([source_hash,*[array_hash(x)for x in (rgb,depth,mask,k,t,np.asarray([explored_depth]))]])).encode()).hexdigest()
        if frame_uid in self.frames:
            if self.frames[frame_uid]!=signature:raise GeometryError("Repeated frame input/pose differs")
            return dict(duplicate=True,changed_tiles=[],allocated_tiles=len(self.records))
        keys=self._candidates(depth,mask,k,t)
        changes={};candidates={};write_contracts={}
        for key in keys:
            tile=self._load(key).fork()
            def collect(value):write_contracts[self.identifier(key)]=value
            tile.integrate(frame_uid,rgb,depth,mask,k,t,source_hash=source_hash,explored_depth=explored_depth,
                _write_collector=collect if collect_write_contracts else None)
            core=self._core_slice()
            if key not in self.records and not np.any((tile.free_count[core]>0)|(tile.surface_count[core]>0)):
                continue
            # A different frame with no core change is not a geometry update.
            old=self._load(key) if key in self.records else None
            if old is not None and all(np.array_equal(v[core],old.arrays()[name][core])for name,v in tile.arrays().items()):
                continue
            if len(set(self.records)|set(changes)|{key})>self.max_total_tiles:
                raise CapacityError("Persistent tile budget exceeded;history is preserved")
            if self.backing is None and len(set(self.records)|set(changes)|{key})>self.max_resident_tiles:
                raise CapacityError("No backing for required tile eviction")
            record=self.backing.save_tile(tile) if self.backing else tile
            changes[key]=record;candidates[key]=tile
        # Storage failures leave only unreachable immutable blobs, never a half-installed manager.
        self.records.update(changes)
        for key,tile in candidates.items():self._cache_tile(key,tile)
        self.frames[frame_uid]=signature
        result=dict(duplicate=False,changed_tiles=[self.identifier(k)for k in sorted(changes)],
                    allocated_tiles=len(self.records),has_evidence=bool(changes))
        if collect_write_contracts:
            result['write_contracts']=dict(input_signature=signature,candidates=[self.identifier(k) for k in keys],tiles=write_contracts)
        return result

    def export(self):
        return dict(origin_G=self.origin_G.tolist(),voxel_size=self.voxel_size,
            core_size=self.core_size.tolist(),halo_cells=self.halo_cells,
            near_m=self.near_m,far_m=self.far_m,max_resident_tiles=self.max_resident_tiles,
            max_total_tiles=self.max_total_tiles,max_candidate_tiles=self.max_candidate_tiles,
            frames=self.frames.copy(),tiles={self.identifier(k):v for k,v in self.records.items()})

    @classmethod
    def restore(cls,state,*,backing):
        fields=("voxel_size","core_size","halo_cells","near_m","far_m",
                "max_resident_tiles","max_total_tiles","max_candidate_tiles")
        result=cls(state["origin_G"],backing=backing,**{k:state[k]for k in fields})
        result.records={cls.parse_identifier(k):v for k,v in state["tiles"].items()}
        if len(result.records)>result.max_total_tiles:raise CapacityError("Restored history exceeds declared tile budget")
        result.frames=dict(state["frames"])
        return result

    def core_arrays(self,tile_id,*,snapshot_id):
        if not isinstance(snapshot_id,str) or not snapshot_id:raise GeometryError("Pinned snapshot identity required")
        key=self.parse_identifier(tile_id)
        if key not in self.records:raise KeyError(tile_id)
        tile=self._load(key);core=self._core_slice()
        result={}
        for name,array in tile.arrays().items():
            result[name]=array[core].copy();result[name].setflags(write=False)
        return dict(submap_id=tile_id,snapshot_id=snapshot_id,arrays=result,
                    T_G_L=tile.T_G_L.copy(),voxel_size=self.voxel_size)
