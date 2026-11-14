"""Evaluation-only mesh binding regressions; no model or oracle policy input."""
import json,hashlib
from pathlib import Path
import pytest

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

@pytest.fixture
def assets(tmp_path):
    root=tmp_path; rel="mp3d/scan/scan.glb"
    glb=root/"data/scene_datasets"/rel;glb.parent.mkdir(parents=True);glb.write_bytes(b"same glb")
    glb.with_suffix(".navmesh").write_bytes(b"wrong original mesh")
    folder=root/"data/derived/navmeshes/awarevln-scene-minimal-endpoint9-v2";folder.mkdir(parents=True)
    mesh=folder/"scan.navmesh";mesh.write_bytes(b"accepted endpoint mesh")
    recipe=root/"configs/navmesh-recipe.json";recipe.parent.mkdir();recipe.write_text(json.dumps(dict(profile_id="awarevln-scene-minimal-endpoint9-v2",scenes={rel:dict(scene_sha256=digest(glb),expected_navmesh_sha256=digest(mesh))})))
    profile=folder/"profile.json";profile.write_text(json.dumps(dict(profile_id="awarevln-scene-minimal-endpoint9-v2",recipe_sha256=digest(recipe),assets={rel:dict(scene_path=str(glb),scene_sha256=digest(glb),navmesh_path=str(mesh),navmesh_sha256=digest(mesh))})))
    binding=dict(project_root=str(root),scene_root=str(root/"data/scene_datasets"),scene_profile=str(profile),scene_profile_sha256=digest(profile))
    return root,profile,binding,glb,mesh

@pytest.mark.parametrize("hook_mode",["on","off"])
def test_public_evaluate_rejects_original_navmesh_before_model_or_gpu(assets,monkeypatch,hook_mode):
    from graphAdapter.evaluation.runner import evaluate
    root,profile,binding,_,_=assets
    monkeypatch.setenv("CASE1_PROTECTION","{}")
    monkeypatch.setenv("POSEADAPTER_BROKER","explicit-unused-entry-probe")
    with pytest.raises(ValueError,match="[Ss]cene|navmesh"):
        evaluate(binding,profile,root/"registry","A",["r2r","rxr_us"],5,root/"outputs/graph_memory/bad",hook_mode=hook_mode)
    assert not(root/"outputs/graph_memory/bad").exists()

def test_frozen_view_selects_endpoint_mesh_and_rejects_drift(assets):
    from case1_runtime.scene_assets import build_scene_view,verify_scene_binding
    root,profile,binding,glb,mesh=assets
    view=build_scene_view(root,json.loads(profile.read_text()));binding['scene_root']=str(view)
    receipt=verify_scene_binding(root,binding)
    assert receipt['assets']['mp3d/scan/scan.glb']['navmesh_sha256']==digest(mesh)
    assert (view/'mp3d/scan/scan.navmesh').resolve()==mesh
    assert (view/'mp3d/scan/scan.glb').resolve()==glb
    assert build_scene_view(root,json.loads(profile.read_text()))==view
    mesh.write_bytes(b'changed')
    with pytest.raises(ValueError,match='drift'):verify_scene_binding(root,binding)

def test_binding_requires_frozen_profile_hash_and_recipe(assets):
    from case1_runtime.scene_assets import build_scene_view,verify_scene_binding
    root,profile,binding,_,_=assets
    binding['scene_root']=str(build_scene_view(root,json.loads(profile.read_text())))
    bad=dict(binding,scene_profile_sha256='0'*64)
    with pytest.raises(ValueError,match='profile'):verify_scene_binding(root,bad)
    (root/'configs/navmesh-recipe.json').write_text('{}')
    with pytest.raises(ValueError,match='recipe'):verify_scene_binding(root,binding)

def test_view_cannot_replace_existing_wrong_link(assets):
    from case1_runtime.scene_assets import build_scene_view
    root,profile,binding,glb,mesh=assets
    view=build_scene_view(root,json.loads(profile.read_text()));alias=view/'mp3d/scan/scan.navmesh'
    alias.unlink();alias.symlink_to(glb.with_suffix('.navmesh'))
    with pytest.raises(ValueError,match='collision'):build_scene_view(root,json.loads(profile.read_text()))

def test_worker_binding_rejects_scene_argument_substitution(assets,tmp_path):
    from case1_runtime.scene_assets import build_scene_view,verify_scene_binding,verify_worker_scenes
    root,profile,binding,_,_=assets
    binding['scene_root']=str(build_scene_view(root,json.loads(profile.read_text())))
    receipt=verify_scene_binding(root,binding);run=root/'outputs/run';run.mkdir(parents=True)
    (run/'run_manifest.json').write_text(json.dumps(dict(scene_assets=receipt)))
    assert verify_worker_scenes(root,run,binding['scene_root'])==receipt
    with pytest.raises(ValueError,match='scene'):verify_worker_scenes(root,run,str(root/'data/scene_datasets'))

@pytest.mark.parametrize("hook_mode",["on","off"])
def test_public_evaluate_corrected_assets_reach_unchanged_stage_gate(assets,monkeypatch,hook_mode):
    from case1_runtime.scene_assets import build_scene_view
    from graphAdapter.evaluation import runner
    root,profile,binding,_,_=assets
    binding['scene_root']=str(build_scene_view(root,json.loads(profile.read_text())))
    stage=root/'stage.json';stage.write_text(json.dumps(dict(feature='map_memory',implementation_status='FROZEN_READY_FOR_SHADOW')))
    monkeypatch.setenv('CASE1_PROTECTION','{}');monkeypatch.setenv('POSEADAPTER_BROKER','explicit-unused-entry-probe')
    reached=[]
    class StageGateProbe(Exception):pass
    def boundary(*args,**kwargs):
        reached.append(kwargs['hook_mode']);raise StageGateProbe('scene verified; later policy/admission gate intentionally not executed')
    monkeypatch.setattr(runner,'verify_map_prerequisites',boundary)
    with pytest.raises(StageGateProbe):runner.evaluate(binding,stage,root/'registry','A',['r2r','rxr_us'],16,root/'outputs/graph_memory/positive',hook_mode=hook_mode)
    assert reached==[hook_mode]
    assert not(root/'outputs/graph_memory/positive').exists()
