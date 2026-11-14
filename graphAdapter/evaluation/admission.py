"""Explicit user-authorized capacity-only FullA admission;no quota success claim."""
from pathlib import Path
import json,hashlib,shutil
from .registry_binding import sha,source_snapshot

def semantic_profile(profile):
    value=json.loads(json.dumps(profile))
    for key in("implementation_status","prerequisite_lock","prerequisite_lock_sha256",
                "full_A_gate","random_validation","storage_lifecycle","storage_admission"):
        value.pop(key,None)
    memory=value.get("map_memory",{})
    for key in("routed_storage","render_on_episode_end"):memory.pop(key,None)
    memory.get("resources",{}).pop("minimum_filesystem_free_bytes",None)
    return value

def verify_capacity_only(root,profile):
    binding=profile["storage_admission"]
    path=Path(binding["contract"])
    if sha(path)!=binding["sha256"]:raise RuntimeError("Capacity-only contract changed")
    contract=json.loads(path.read_bytes())
    if(contract.get("mode")!="USER_AUTHORIZED_CAPACITY_ONLY"or contract.get("quota_enforced")is not False
        or contract.get("user_message_id")!="01a1b9e0-afff-7d33-a791-f1de310e1d20"):
        raise RuntimeError("Explicit capacity-only authority missing")
    frozen,identity=source_snapshot(root,map_stage=True)
    if identity!=contract["source_sha256"]:raise RuntimeError("Current shared source differs from run contract")
    baseline=Path(contract["baseline_profile"])
    if sha(baseline)!=contract["baseline_profile_sha256"]:raise RuntimeError("Accepted baseline profile changed")
    if semantic_profile(profile)!=semantic_profile(json.loads(baseline.read_bytes())):
        raise RuntimeError("Model/policy/geometry/input budget changed")
    original=Path(contract["baseline_pair_report"])
    if sha(original)!=contract["baseline_pair_sha256"]:raise RuntimeError("Accepted paired evidence changed")
    evidence=json.loads(original.read_bytes())
    if evidence["status"]!="PASS_ENGINEERING"or evidence["hard_contract_errors"]or evidence["pairs"]!=32:
        raise RuntimeError("Accepted random32 evidence missing")
    for item in contract["asset_locks"]:
        path=Path(item["path"])
        if sha(path)!=item["sha256"]:raise RuntimeError("Pinned asset lock changed")
        asset=json.loads(path.read_bytes())
        for row in asset.get("weights",[])+asset.get("model_small_and_native",[])+asset.get("files",[]):
            if sha(Path(row["path"]))!=row["sha256"]:raise RuntimeError("Pinned runtime/model/scene asset changed")
    required=contract["capacity_required_bytes"]
    if shutil.disk_usage(root).free<required:
        raise RuntimeError("Current capacity below frozen run requirement")
    return contract

def verify_release4_production(root,profile):
    """New explicit35-stream release authority; never forge acceptance of old meshes."""
    entry=profile['production_admission'];path=Path(entry['contract'])
    if sha(path)!=entry['sha256']:raise RuntimeError('Production contract changed')
    contract=json.loads(path.read_bytes())
    if contract.get('user_message_id')!='01a1bae3-2c94-7440-9802-db171540f6fe':raise RuntimeError('Production authority missing')
    if source_snapshot(root,map_stage=True)[1]!=contract['source_sha256']:raise RuntimeError('Production source changed')
    acceptance=Path(contract['acceptance']);
    if sha(acceptance)!=contract['acceptance_sha256']:raise RuntimeError('Independent35 acceptance changed')
    from graphAdapter.observation_pose.production import verify_package
    verify_package(profile['pose_package'])
    routing=profile['storage_lifecycle']['routing'];plan=json.loads((Path(routing['root'])/'retention_plan.json').read_bytes())
    if plan.get('production_schema')!='release4_endpoint_v1':raise RuntimeError('Required endpoint audit schema missing')
    if profile.get('pose_sampling')!='release4_12' or profile['sensor_clock']['rate_hz']!=120:raise RuntimeError('Release4 sampling changed')
    if any(profile.get(k)for k in ['memory_injection','navigation','frontier']):raise RuntimeError('Only001 shadow authorized')
    # Pin the entire effective profile, including package/geometry/budget/retention contracts.
    material=json.loads(json.dumps(profile));material.pop('production_admission',None)
    if hashlib.sha256(json.dumps(material,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=contract['effective_profile_sha256']:
        raise RuntimeError('Frozen production profile changed')
    if shutil.disk_usage(root).free<contract['minimum_free_bytes']:raise RuntimeError('Production free-space admission failed')
    for item in contract['asset_locks']:
        p=Path(item['path'])
        if sha(p)!=item['sha256']:raise RuntimeError('Model/runtime lock changed')
        lock=json.loads(p.read_bytes())
        for row in lock.get('weights',[])+lock.get('model_small_and_native',[])+lock.get('files',[]):
            if sha(Path(row['path']))!=row['sha256']:raise RuntimeError('Model/runtime asset drift')
    return contract
