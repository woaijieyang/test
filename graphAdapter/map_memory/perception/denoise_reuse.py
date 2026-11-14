"""Reuse a DBSCAN keep-all result for an exactly equal unordered sampled XYZ cloud."""
import numpy as np
from evomemnav.third_party.conceptgraph.slam.utils import get_bounding_box, pcd_denoise_dbscan


class KeepAllClouds:
    """One scene revision. Values are immutable and may be shared with a pending fork."""
    def __init__(self):
        self.entries = {}
        self.bytes = 0

    def fork(self):
        other = KeepAllClouds()
        other.entries = self.entries.copy()
        other.bytes = self.bytes
        return other

    def discard(self, object_id):
        entry = self.entries.pop(object_id, None)
        if entry is not None:
            self.bytes -= entry[1].nbytes

    def apply(self, objects, cfg, limit):
        hits = misses = hit_points = 0
        eps = cfg["dbscan_eps"]
        minimum = cfg["dbscan_min_points"]
        params = (eps, minimum)
        for oid in set(self.entries).difference(objects):
            self.discard(oid)
        for oid, obj in objects.items():
            original = obj["pcd"]
            if len(original.points) > 1:
                sampled = original.voxel_down_sample(cfg["downsample_voxel_size"])
                cleaned = sampled
                if cfg["dbscan_remove_noise"]:
                    xyz = np.asarray(sampled.points)
                    # For min_points >= 5 the upstream <5 fallback cannot discard a
                    # distinct core component. Restrict reuse to ordinary XYZ/RGB.
                    eligible = (minimum >= 5 and 0 < xyz.nbytes <= limit and np.isfinite(xyz).all()
                                and not sampled.has_normals() and not sampled.has_covariances())
                    ordered = None
                    if eligible:
                        bits = xyz.view(np.uint64)
                        ordered = bits[np.lexsort((bits[:,2], bits[:,1], bits[:,0]))]
                    old = self.entries.get(oid)
                    if (old is not None and ordered is not None and old[0] == params
                            and np.array_equal(ordered,old[1])):
                        hits += 1
                        hit_points += len(xyz)
                    else:
                        misses += 1
                        self.discard(oid)
                        cleaned = pcd_denoise_dbscan(sampled, eps=eps, min_points=minimum)
                        if (ordered is not None and self.bytes + ordered.nbytes <= limit
                                and np.array_equal(xyz, np.asarray(cleaned.points))
                                and np.array_equal(np.asarray(sampled.colors), np.asarray(cleaned.colors))):
                            ordered.setflags(write=False)
                            self.entries[oid] = (params, ordered)
                            self.bytes += ordered.nbytes
                obj["pcd"] = cleaned if len(cleaned.points) >= 4 else original
            obj["bbox"] = get_bounding_box(cfg["spatial_sim_type"],obj["pcd"])
            obj["bbox"].color = [0,1,0]
        return dict(hits=hits, misses=misses, reused_points=hit_points, retained_bytes=self.bytes)
