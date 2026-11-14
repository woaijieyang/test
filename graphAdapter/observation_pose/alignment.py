"""Single depth conversion and geometric registration, without synthetic hole filling."""
from dataclasses import dataclass
import hashlib,json
from dataclasses import asdict
import numpy as np
from poseAdapter.coordinate.calibration import Calibration

def array_hash(value):
    a = np.ascontiguousarray(value)
    h = hashlib.sha256()
    h.update(str(a.dtype).encode())
    h.update(str(a.shape).encode())
    h.update(a.tobytes())
    return h.hexdigest()

def intrinsic(cal):
    return np.array([[cal.fx, 0, cal.cx], [0, cal.fy, cal.cy], [0, 0, 1.]], dtype=float)

@dataclass(frozen=True)
class AlignedRGBD:
    rgb: np.ndarray
    depth: np.ndarray
    valid_mask: np.ndarray
    source_pixel_map: np.ndarray
    calibration: Calibration
    alignment_method: str
    raw_rgb_hash: str
    raw_depth_hash: str
    aligned_depth_hash: str
    calibration_hash: str = ""

class RGBDAlignmentBridge:
    def __init__(self, rgb_cal, depth_cal, depth_spec, T_rgb_depth, *, invalid_values=(), synchronized=True):
        self.rgb_cal, self.depth_cal, self.spec = rgb_cal, depth_cal, depth_spec
        from poseAdapter.coordinate.transforms import checked_transform
        self.T = checked_transform(T_rgb_depth)
        if not synchronized:
            raise ValueError("Unsynchronized RGB-D is unavailable")
        self.invalid_values = tuple(invalid_values)
        def record(cal):
            value=asdict(cal);value["T_base_camera"]=cal.T_base_camera.tolist();return value
        manifest=dict(rgb=record(rgb_cal),depth=record(depth_cal),depth_spec=asdict(depth_spec),
                      T_rgb_depth=self.T.tolist(),invalid_values=self.invalid_values,synchronized=synchronized)
        self.calibration_hash=hashlib.sha256(json.dumps(manifest,sort_keys=True,allow_nan=False).encode()).hexdigest()

    def align(self, rgb, depth):
        rgb = np.asarray(rgb)
        raw = np.asarray(depth)
        raw_depth_hash = array_hash(raw)
        if raw.shape == (self.depth_cal.height, self.depth_cal.width, 1):
            raw = raw[:, :, 0]
        if rgb.shape != (self.rgb_cal.height, self.rgb_cal.width, 3) or rgb.dtype != np.uint8:
            raise ValueError("RGB shape/dtype mismatch")
        valid = np.isfinite(raw)
        for sentinel in self.invalid_values:
            valid &= raw != sentinel
        if self.spec.units == "normalized":
            valid &= (raw >= 0) & (raw <= 1)
        else:
            scale = .001 if self.spec.units == "millimeters" else 1.
            valid &= (raw * scale >= self.spec.near_m) & (raw * scale <= self.spec.far_m)
        # metric_copy validates full normalized input; replace declared invalid values privately.
        conversion_input = raw.copy()
        conversion_input[~valid] = 0
        metric = self.spec.metric_copy(conversion_input, self.depth_cal)
        valid &= np.isfinite(metric) & (metric > 0)
        h, w = self.rgb_cal.height, self.rgb_cal.width
        output = np.zeros((h, w), np.float32)
        source = np.full((h, w, 2), -1, np.int32)
        if np.allclose(self.T, np.eye(4), atol=1e-12):
            y, x = np.indices((h, w))
            pixels = np.stack([x.ravel(), y.ravel(), np.ones(h*w)])
            rays = intrinsic(self.depth_cal) @ np.linalg.inv(intrinsic(self.rgb_cal)) @ pixels
            u = np.rint(rays[0]).astype(int)
            v = np.rint(rays[1]).astype(int)
            inside = (u >= 0) & (u < self.depth_cal.width) & (v >= 0) & (v < self.depth_cal.height)
            dst = np.flatnonzero(inside)
            dst = dst[valid[v[dst], u[dst]]]
            output.ravel()[dst] = metric[v[dst], u[dst]]
            source.reshape(-1, 2)[dst] = np.stack([v[dst], u[dst]], axis=1)
            method = "coincident_ray_nearest_valid_no_hole_fill"
        else:
            v, u = np.nonzero(valid)
            points = np.linalg.inv(intrinsic(self.depth_cal)) @ np.stack([u, v, np.ones(len(u))])
            points *= metric[v, u]
            points = self.T[:3, :3] @ points + self.T[:3, 3:4]
            front = points[2] > 0
            projected = intrinsic(self.rgb_cal) @ points[:, front]
            projected[:2] /= projected[2]
            du, dv = np.rint(projected[:2]).astype(int)
            z = points[2, front]
            su, sv = u[front], v[front]
            inside = (du >= 0) & (du < w) & (dv >= 0) & (dv < h)
            # Far first, then overwrite with closest surface. Stable ties preserve determinism.
            for i in np.argsort(-z, kind="stable"):
                if inside[i]:
                    output[dv[i], du[i]] = z[i]
                    source[dv[i], du[i]] = (sv[i], su[i])
            method = "extrinsic_projection_nearest_z_buffer"
        result_rgb = np.array(rgb, copy=True)
        mask = output > 0
        for a in (result_rgb, output, mask, source):
            a.setflags(write=False)
        return AlignedRGBD(result_rgb, output, mask, source, self.rgb_cal, method,
                           array_hash(rgb), raw_depth_hash, array_hash(output), self.calibration_hash)


def archive_aligned_product(frame_folder,aligned,*,retain_source_pixel_map=True):
    """Persist IPC inputs; the source map is an optional reproducible diagnostic.

    Compute/validate the entire aligned product regardless of storage choice.
    RGB/depth,calibration and typed source-map hash preserve exact replay.
    """
    from pathlib import Path
    import os
    if type(retain_source_pixel_map)is not bool:
        raise ValueError('Explicit boolean source-map retention required')
    folder=Path(frame_folder)
    products=[('aligned_depth',aligned.depth),('depth_valid_mask',aligned.valid_mask)]
    if retain_source_pixel_map:products.append(('source_pixel_map',aligned.source_pixel_map))
    for name,array in products:
        with(folder/(name+'.npy')).open('xb')as stream:
            np.save(stream,array,allow_pickle=False);stream.flush();os.fsync(stream.fileno())
    return str(folder/'aligned_depth.npy'),dict(aligned_depth_hash=aligned.aligned_depth_hash,
        valid_mask_hash=hashlib.sha256(np.ascontiguousarray(aligned.valid_mask).tobytes()).hexdigest(),
        valid_mask_typed_hash=array_hash(aligned.valid_mask),source_pixel_map_hash=array_hash(aligned.source_pixel_map),
        source_pixel_map_storage='npy'if retain_source_pixel_map else'regenerable_from_raw_and_calibration',
        calibration_hash=aligned.calibration_hash)

def verify_aligned_product_archive(frame_folder,recomputed,alignment,*,allow_legacy=False):
    """Read-side contract for saved or explicitly regenerable source maps."""
    from pathlib import Path
    folder=Path(frame_folder)
    declaration=alignment.get("source_pixel_map_storage")
    map_hash=alignment.get("source_pixel_map_hash")
    mask_hash=alignment.get("valid_mask_typed_hash")
    legacy=declaration is None and map_hash is None and mask_hash is None
    if legacy:
        if not allow_legacy:raise ValueError("Legacy alignment format requires explicit source compatibility")
    else:
        if declaration not in {"npy","regenerable_from_raw_and_calibration"}:
            raise ValueError("Unknown/missing source-map storage declaration")
        if map_hash!=array_hash(recomputed.source_pixel_map):
            raise ValueError("Regenerated source pixel map typed hash mismatch")
        if mask_hash!=array_hash(recomputed.valid_mask):
            raise ValueError("Regenerated valid mask typed hash mismatch")
        if alignment.get("calibration_hash")!=recomputed.calibration_hash:
            raise ValueError("Alignment recipe identity mismatch")
    mask=folder/"depth_valid_mask.npy"
    if not mask.exists()and not legacy:raise ValueError("Declared valid mask file missing")
    if mask.exists()and array_hash(np.load(mask,allow_pickle=False))!=array_hash(recomputed.valid_mask):
        raise ValueError("Recorded valid mask differs")
    source=folder/"source_pixel_map.npy"
    if declaration=="npy"and not source.exists():raise ValueError("Declared NPY source pixel map missing")
    if source.exists()and array_hash(np.load(source,allow_pickle=False))!=array_hash(recomputed.source_pixel_map):
        raise ValueError("Recorded source pixel map differs")
    return dict(format="legacy_optional_untyped"if legacy else"typed_declared_storage",
        source_pixel_map_storage=declaration or"legacy_optional",
        source_pixel_map_hash=array_hash(recomputed.source_pixel_map),
        valid_mask_typed_hash=array_hash(recomputed.valid_mask),
        source_map_file_present=source.exists())
