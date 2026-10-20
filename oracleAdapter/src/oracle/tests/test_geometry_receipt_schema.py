from pathlib import Path
import hashlib
import json
import struct
import tempfile
import unittest
from oracle.verification.source_scene import SourceScene


class GeometryReceiptSchemaTests(unittest.TestCase):
    def fixture(self,root):
        geometry=root/'triangles.bin'
        geometry.write_bytes(struct.pack('<ii9f3i',3,1,.05,.4,-.2,.05,1.2,-.2,.05,.4,.2,0,1,2))
        sha=hashlib.sha256(geometry.read_bytes()).hexdigest();scene='a'*64
        flat=root/'flat.json';legacy=root/'legacy.json'
        flat.write_text(json.dumps(dict(native_geometry_path=str(geometry),native_geometry_sha256=sha,scene_sha256=scene)))
        legacy.write_text(json.dumps(dict(status='NATIVE_STAGE_DIAGNOSIS_ONLY',scene='fixture',native_byte_control_match=True,
            native_triangle_dump_sha256=sha,scene_sha256=scene,vertices=3,triangles=1)))
        catalog=dict(scene='fixture',scene_sha256=scene,native_geometry_path=str(geometry),native_geometry_sha256=sha,native_vertices=3,native_triangles=1)
        protocol=dict(body_radius_m=.1,body_height_m=1.5,foot_epsilon_m=.00001,radial_epsilon_m=.000001)
        return flat,legacy,catalog,protocol

    def test_catalog_bound_legacy_receipt_loads_identical_geometry_and_contact(self):
        with tempfile.TemporaryDirectory() as tmp:
            flat,legacy,catalog,protocol=self.fixture(Path(tmp))
            control=SourceScene(flat,hashlib.sha256(flat.read_bytes()).hexdigest(),protocol)
            try:
                candidate=SourceScene(legacy,hashlib.sha256(legacy.read_bytes()).hexdigest(),protocol,catalog=catalog)
            except (TypeError,KeyError) as exc:
                self.fail('Catalog-bound legacy native dump is not supported: '+repr(exc))
            self.assertEqual(control.triangles.tobytes(),candidate.triangles.tobytes())
            self.assertEqual(control.contact([0,0,0],[0,0,0],certificate=True),candidate.contact([0,0,0],[0,0,0],certificate=True))
            self.assertIsNotNone(candidate.contact([0,0,0],[0,0,0]))

    def test_legacy_receipt_cannot_guess_a_path_without_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            _,legacy,_,protocol=self.fixture(Path(tmp))
            with self.assertRaises(ValueError):SourceScene(legacy,hashlib.sha256(legacy.read_bytes()).hexdigest(),protocol)

    def test_catalog_hash_or_scene_disagreement_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            _,legacy,catalog,protocol=self.fixture(Path(tmp))
            for field in ('native_geometry_sha256','scene_sha256'):
                bad={**catalog,field:'b'*64}
                with self.assertRaises(ValueError):SourceScene(legacy,hashlib.sha256(legacy.read_bytes()).hexdigest(),protocol,catalog=bad)

    def test_flat_receipt_cannot_be_retargeted_by_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            flat,_,catalog,protocol=self.fixture(Path(tmp));catalog['native_geometry_path']=str(Path(tmp)/'different.bin')
            with self.assertRaises(ValueError):SourceScene(flat,hashlib.sha256(flat.read_bytes()).hexdigest(),protocol,catalog=catalog)
