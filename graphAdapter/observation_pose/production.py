"""Run-bound independent pose package checks; no model or locator implementation."""
from pathlib import Path
import hashlib,json,sys,zipfile
ROOT=Path(__file__).resolve().parents[3]
SITE=(ROOT/'runtime/pose/standalone-site-v0.1.5rc4').resolve()
WHEEL_SHA='1670ccc876bfb509b5801f7e3bc3bee12fd0b4dcf668ea77838a5e0f123ebcb1'
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def verify_package(lock,*,actual_import=False):
    if Path(lock['parent']).resolve()!=SITE or lock['wheel_sha256']!=WHEEL_SHA:
        raise RuntimeError('Release4 requires the sealed independent0.1.5rc4 mapping-interface package')
    wheel=Path(lock['wheel'])
    if digest(wheel)!=WHEEL_SHA:raise RuntimeError('Pose wheel changed')
    expected={x['relative']:x['sha256']for x in lock['files']}
    with zipfile.ZipFile(wheel)as archive:
        files={n:hashlib.sha256(archive.read(n)).hexdigest()for n in archive.namelist()if n.startswith('poseAdapter/')and not n.endswith('/')}
    if files!=expected:raise RuntimeError('Pose wheel file closure changed')
    for relative,sha in files.items():
        if digest(SITE/relative)!=sha:raise RuntimeError('Installed pose file changed: '+relative)
        if digest(ROOT/'src'/relative)!=sha:
            raise RuntimeError('Frozen source differs from independent wheel: '+relative)
    loaded={}
    if actual_import:
        for name,module in list(sys.modules.items()):
            if name=='poseAdapter'or name.startswith('poseAdapter.'):
                path=getattr(module,'__file__',None)
                if path:
                    path=Path(path).resolve()
                    if not path.is_relative_to(SITE/'poseAdapter'):raise RuntimeError('Mixed pose import: '+str(path))
                    relative=str(path.relative_to(SITE))
                    if files.get(relative)!=digest(path):raise RuntimeError('Actual pose module differs from wheel')
                    loaded[name]=dict(path=str(path),sha256=files[relative])
        if 'poseAdapter'not in loaded:raise RuntimeError('Actual pose import missing')
    return dict(wheel=str(wheel),wheel_sha256=WHEEL_SHA,parent=str(SITE),python_files=sum(name.endswith(".py") for name in files),loaded=loaded)

def audit_samples(packets_path,flow_path,*,required=True,allow_legacy=False):
    """Before source reclamation, verify every real sample and endpoint mapping."""
    packets=[json.loads(l)for l in Path(packets_path).read_text().splitlines()if l]
    events=[json.loads(l)for l in Path(flow_path).read_text().splitlines()if l]
    sampled=[x for x in events if x['kind']=='pose_sample'or(x['kind']=='pose'and x.get('sampling_contract')=='release4_12')]
    if not sampled:
        if required or not allow_legacy:raise RuntimeError('Required production pose sampling events missing')
        return dict(mode='legacy_endpoint_source',explicit_frozen_compatibility=True)
    canonical={};partial={};sequence=0
    for row in sampled:
        sequence+=1
        seq=row.get('sequence',row.get('sensor_sequence'))
        stamp=row.get('timestamp_ns',(row.get('pose')or{}).get('timestamp_ns'))
        if seq!=sequence or stamp!=round(sequence*1e9/120):raise RuntimeError('Sample sequence/timestamp contract failed')
        if row['kind']=='pose_sample':partial.setdefault(row['target_frame_uid'],[]).append(row['sample_index'])
        else:
            if row['frame_uid']in canonical:raise RuntimeError('Duplicate canonical pose endpoint')
            canonical[row['frame_uid']]=seq
    expected=0
    for i,packet in enumerate(packets):
        uid=packet['frame_uid'];action=packet['action']['action_id'];count=1 if i==0 or action==0 else 12
        expected+=count
        if canonical.get(uid)!=expected or packet['sensor_timestamp_ns']!=round(expected*1e9/120):
            raise RuntimeError('Host endpoint bound to wrong pose sample')
        if partial.pop(uid,[])!=list(range(1,count)):raise RuntimeError('Missing/extra pose-only subframes')
    if partial or len(canonical)!=len(packets) or sequence!=expected:raise RuntimeError('Unbound pose samples')
    return dict(mode='release4_12',status='VERIFIED',samples=sequence,host_endpoints=len(packets),
        extra_pose_views=sequence-len(packets),intermediate_arrays_archived=False,logical_rate_hz=120)


# Numeric/acquisition settings are unchanged from the accepted release4 run.
# Package/API identity is checked separately, so interface additions do not
# silently authorize different sensor clocks or estimator profiles.
POSE_CONFIGURATION_KEYS=("pose_sampling","sensor_clock","pose_backend","frontend_profile","rtab_registration_profile","pose_options")
POSE_CONFIGURATION_SHA256="d6fcd8145e1810c355e7c1a7120dd3262c86edc21dc0d1a666cef37ef0565644"

def verify_pose_configuration(profile):
    material={key:profile.get(key) for key in POSE_CONFIGURATION_KEYS}
    actual=hashlib.sha256(json.dumps(material,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    if actual!=POSE_CONFIGURATION_SHA256:
        raise RuntimeError("Pose acquisition/backend configuration differs from accepted release4")
    if not isinstance(profile.get("pose_package"),dict):
        raise RuntimeError("Continuous mapping requires the declared independent PoseAdapter package")
    return dict(status="VERIFIED",configuration_sha256=actual,sampling="release4_12",logical_rate_hz=120)
