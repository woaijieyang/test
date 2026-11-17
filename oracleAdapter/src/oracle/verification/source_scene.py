"""Fixed-protocol source feasibility, separate from route generation."""
import hashlib
import json
from pathlib import Path
import struct

from oracle.verification.linear_sweep import triangle_linear_sweep_distance
from oracle.verification.contact_certificate import linear_sweep_witness, verify_witness


def geometry_descriptor(receipt,catalog=None):
    """Resolve only explicit supported receipts; never guess a dump filename."""
    if all(k in receipt for k in ('native_geometry_path','native_geometry_sha256','scene_sha256')):
        descriptor={k:receipt[k] for k in ('native_geometry_path','native_geometry_sha256','scene_sha256')}
        schema='flat_native_geometry'
    elif (catalog is not None and receipt.get('status')=='NATIVE_STAGE_DIAGNOSIS_ONLY'
          and receipt.get('native_byte_control_match') is True
          and 'native_triangle_dump_sha256' in receipt):
        if (receipt.get('scene')!=catalog['scene'] or receipt.get('scene_sha256')!=catalog['scene_sha256']
            or receipt['native_triangle_dump_sha256']!=catalog['native_geometry_sha256']
            or receipt.get('vertices')!=catalog['native_vertices'] or receipt.get('triangles')!=catalog['native_triangles']):
            raise ValueError('Legacy native receipt differs from frozen catalog')
        descriptor={k:catalog[k] for k in ('native_geometry_path','native_geometry_sha256','scene_sha256')}
        schema='catalog_bound_native_stage_dump'
    else:
        raise ValueError('Unsupported native geometry receipt; explicit catalog-bound identity required')
    if catalog is not None:
        if (Path(descriptor['native_geometry_path']).resolve()!=Path(catalog['native_geometry_path']).resolve()
            or descriptor['native_geometry_sha256']!=catalog['native_geometry_sha256']
            or descriptor['scene_sha256']!=catalog['scene_sha256']):
            raise ValueError('Native geometry receipt and catalog disagree')
    return descriptor,schema


class SourceScene:
    def __init__(self, receipt_path, receipt_sha256, protocol, *, catalog=None):
        import numpy as np
        self.np = np
        p = Path(receipt_path)
        if hashlib.sha256(p.read_bytes()).hexdigest() != receipt_sha256:
            raise RuntimeError("Native geometry receipt drift")
        receipt = json.loads(p.read_text())
        descriptor,self.receipt_schema=geometry_descriptor(receipt,catalog)
        raw = Path(descriptor["native_geometry_path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != descriptor["native_geometry_sha256"]:
            raise RuntimeError("Native geometry bytes changed")
        nv, nt = struct.unpack("<ii", raw[:8])
        if min(nv, nt) < 1 or len(raw) != 8 + 12 * nv + 12 * nt:
            raise ValueError("Invalid native-exported geometry layout")
        vertices = np.frombuffer(raw, dtype="<f4", count=nv * 3, offset=8).reshape(nv, 3)
        indices = np.frombuffer(raw, dtype="<i4", count=nt * 3, offset=8 + 12 * nv).reshape(nt, 3)
        self.triangles = vertices[indices].astype(float)
        self.low = self.triangles.min(axis=1)
        self.high = self.triangles.max(axis=1)
        self.protocol = dict(protocol)
        self.geometry_sha256 = descriptor["native_geometry_sha256"]
        self.scene_sha256 = descriptor["scene_sha256"]
        self.queries = self.triangle_checks = 0

    def _broadphase_indices(self, low, high, radius, height, foot):
        return self.np.flatnonzero(
            (self.low[:, 0] < high[0] + radius) & (self.high[:, 0] > low[0] - radius)
            & (self.low[:, 2] < high[2] + radius) & (self.high[:, 2] > low[2] - radius)
            & (self.low[:, 1] < high[1] + height) & (self.high[:, 1] > low[1] + foot))

    def contact(self, start, end, certificate=False, arithmetic="float_projection"):
        """Use the historical open-slab broadphase and unchanged exact sweep.

        An optional rational witness checks a positive contact without calling
        the distance implementation. Shared geometry/model assumptions remain.
        """
        np = self.np
        if arithmetic not in {"float_projection", "rational_hull"}:
            raise ValueError("Unknown geometry arithmetic")
        a, b = np.asarray(start, dtype=float), np.asarray(end, dtype=float)
        if not np.isfinite([a, b]).all():
            raise ValueError("Nonfinite query")
        low, high = np.minimum(a, b), np.maximum(a, b)
        radius = self.protocol["body_radius_m"]
        height = self.protocol["body_height_m"]
        foot = self.protocol["foot_epsilon_m"]
        threshold = radius - self.protocol["radial_epsilon_m"]
        indices = self._broadphase_indices(low, high, radius, height, foot)
        self.queries += 1
        for index in indices:
            triangle = self.triangles[index]
            self.triangle_checks += 1
            if arithmetic == "rational_hull":
                witness = linear_sweep_witness(triangle, a, b, height=height, foot_epsilon=foot)
                if witness is not None and verify_witness(triangle, a, b, witness, radius=threshold,
                                                         height=height, foot_epsilon=foot):
                    return {"triangle": int(index), "distance": witness["distance"],
                            "geometry_sha256": self.geometry_sha256, "witness": witness,
                            "arithmetic": arithmetic}
                continue
            distance = triangle_linear_sweep_distance(triangle, a, b, height=height, foot_epsilon=foot)
            if distance < threshold:
                record = {"triangle": int(index), "distance": distance,
                          "geometry_sha256": self.geometry_sha256}
                if certificate:
                    witness = linear_sweep_witness(triangle, a, b, height=height, foot_epsilon=foot)
                    if witness is None or not verify_witness(triangle, a, b, witness, radius=threshold,
                                                             height=height, foot_epsilon=foot):
                        raise RuntimeError("Positive contact not confirmed by independent rational witness")
                    record["witness"] = witness
                return record
        return None
