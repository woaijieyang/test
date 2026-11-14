"""Independent final snapshots, phase retention and cold verification; no model policy."""
from pathlib import Path
from collections.abc import Mapping
import argparse,ctypes,hashlib,itertools,json,os,platform,shutil,subprocess,sys,uuid
import numpy as np
from .store import load_episode,identity
from .pages import BundlePages
from .archive import canonical,digest,owned_references,_verify_ref,sync_dir,decode_arrays
from .lifecycle import pack_tree,unpack_tree,assert_no_open_files,atomic_json,sha
from ..visualization import render_episode
PROJECT_ROOT=Path(os.environ.get('AWAREVLN_ROOT',Path(__file__).resolve().parents[4])).resolve()

def plain(value):
    if isinstance(value,Mapping):return {k:plain(v)for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [plain(v)for v in value]
    return value

def retention_policy(context):
    """Unknown or insufficiently accepted phases always keep every produced map."""
    context=dict(context or {})
    if context.get('phase')!='post_acceptance_nonformal' or context.get('testing')is not False or context.get('formal_evaluation')is not False:
        return dict(mode='all_produced_final_maps',reason='test/formal/pending/unknown defaults to all')
    receipt=context.get('acceptance_receipt')
    if not isinstance(receipt,dict)or not {'path','sha256'}<=set(receipt):return dict(mode='all_produced_final_maps',reason='No verified complete acceptance receipt')
    path=Path(receipt['path'])
    if not path.is_file()or hashlib.sha256(path.read_bytes()).hexdigest()!=receipt['sha256']:return dict(mode='all_produced_final_maps',reason='Acceptance receipt missing or changed')
    try:document=json.loads(path.read_bytes())
    except (OSError,ValueError,TypeError):return dict(mode='all_produced_final_maps',reason='Unreadable acceptance receipt')
    if not isinstance(document,dict):return dict(mode='all_produced_final_maps',reason='Malformed acceptance receipt')
    if document.get('stage')!='001'or document.get('status')!='ACCEPTED'or document.get('acceptance_complete')is not True:
        return dict(mode='all_produced_final_maps',reason='Stage001 not completely accepted')
    return dict(mode='predeclared_demo',maps_per_dataset=8,reason='Explicit post-acceptance nonformal non-test phase with verified receipt')

def select_members(entries,context):
    policy=retention_policy(context)
    if policy['mode']=='all_produced_final_maps':return list(entries),policy
    if any(sum(e['member'][0]==d for e in entries)<policy['maps_per_dataset']for d in ['r2r','rxr_us']):return list(entries),dict(mode='all_produced_final_maps',reason='Insufficient declared members for balanced demos')
    selected=[]
    for dataset in ['r2r','rxr_us']:
        domain=[e for e in entries if e['member'][0]==dataset]
        selected.extend(sorted(domain,key=lambda e:digest(canonical(e['member'])))[:policy['maps_per_dataset']])
    return selected,policy

def requires_final_map(plan,entry):
    selected,_=select_members(plan['entries'],plan.get('final_map_policy'))
    return any(e['key']==entry['key']for e in selected)

def footprint(root):
    files=[p for p in Path(root).rglob('*')if p.is_file()]
    return dict(files=len(files),logical_bytes=sum(p.stat().st_size for p in files),allocated_bytes=sum(p.stat().st_blocks*512 for p in files))

def logical(reader):
    graph=json.loads(canonical(reader._graph));facts={x['uid']:x['refs']for x in reader.manifest['observations']}
    if hasattr(reader,'pages'):
        bundle=reader.pages.graph(force=True)
        return {k:bundle[k]for k in ('graph','facts','executions','entities','aliases')}
    executions={digest(canonical(x)):x for x in plain(reader.get_trace())}
    return dict(graph=graph,facts=facts,executions=executions,entities={identity(x['epoch'],x['id']):x for x in graph.get('entities',[])},aliases={identity(x['epoch'],x['src']):x for x in graph.get('aliases',[])})

def export_final(source,destination,*,revision="CURRENT"):
    source=Path(source).resolve();final=Path(destination).absolute()
    if final.exists():raise FileExistsError(final)
    final.parent.mkdir(parents=True,exist_ok=True)
    destination=final.parent/('.'+final.name+'.pending-'+uuid.uuid4().hex)
    reader=load_episode(source,revision=revision)
    writer=None
    try:
        before=reader.verify(hashes=True,references=True);bundle=logical(reader)
        public=dict(versions=dict(reader.versions),cutoff=dict(reader.cutoff),episode_uid=reader.identity['episode_uid'],storage_codec='literal_history_v1')
        bundle['public']=public
        refs=owned_references(bundle)
        writer=BundlePages(destination,create=True)
        shutil.copyfile(source/'episode_identity.json',destination/'episode_identity.json')
        if(source/'episode_scope.json').is_file():shutil.copyfile(source/'episode_scope.json',destination/'episode_scope.json')
        for ref in refs:
            src=_verify_ref(source,ref);target=destination/ref['path']
            if not target.resolve().is_relative_to(destination.resolve()):raise ValueError('Export reference outside final root')
            target.parent.mkdir(parents=True,exist_ok=True)
            with src.open('rb')as a,target.open('xb')as b:shutil.copyfileobj(a,b);b.flush();os.fsync(b.fileno())
        changes={k:bundle[k]for k in ('facts','executions','entities','aliases')}
        pointer=writer.publish(bundle,digest(canonical(public)),public=public,changes=changes)
        writer.close();writer=None
        report=dict(schema='final_snapshot_export_v1',source_snapshot_id=reader.snapshot_id,final_snapshot_id=pointer['snapshot_id'],episode_identity=reader.identity,versions=public['versions'],cutoff=public['cutoff'],source_inspection=before,
          logical_hashes={k:digest(canonical(bundle[k]))for k in ('graph','facts','executions','entities','aliases')},reference_files=len(refs),reference_logical_bytes=sum(x['bytes']for x in refs),source_footprint=footprint(source),
          retention='One independent root revision plus complete referenced immutable material; no original revision or shared blob deleted',capabilities=['final_snapshot','queryable','raw_observations'],not_claimed=['prior derived revision history','native SLAM resume','full fusion source replay'])
        (destination/'FINAL_EXPORT.json').write_bytes(canonical(report));sync_dir(destination)
    finally:
        if writer is not None:writer.close()
        reader.close()
    verification=verify_final(destination)
    report['independent_verification']=verification;report['final_footprint']=footprint(destination)
    (destination/'FINAL_EXPORT.json').write_bytes(canonical(report));sync_dir(destination)
    os.rename(destination,final);sync_dir(final.parent);return report

def verify_final(root):
    root=Path(root);record=json.loads((root/'FINAL_EXPORT.json').read_bytes());reader=load_episode(root)
    try:
        checked=reader.verify(hashes=True,references=True);bundle=logical(reader)
        for k,h in record['logical_hashes'].items():
            if digest(canonical(bundle[k]))!=h:raise ValueError('Exported logical field differs: '+k)
        for uid in bundle['graph']['views']:
            view=reader.get_view(uid,include_images=True,include_depth=True)
            if view['capture']['frame_uid']!=uid:raise ValueError('View capture identity differs')
        for key in bundle['graph'].get('tiles',{}):reader.get_geometry(key)
        for entity in bundle['graph'].get('entities',[]):reader.get_object(entity['epoch'],entity['id'])
        if len(list(reader.iter_verified_history()))!=1:raise ValueError('Final export has unexpected derived history')
        refs=owned_references(bundle)
        for ref in refs:_verify_ref(root,ref)
        return dict(status='VERIFIED',snapshot_id=reader.snapshot_id,logical_fields_equal=True,views=len(bundle['graph']['views']),tiles=len(bundle['graph'].get('tiles',{})),objects=len(bundle['graph'].get('scene_state',{}).get('objects',[])),anchors=len(bundle['graph'].get('vsm',{}).get('anchors',{})),visibility_edges=len(bundle['graph'].get('vsm',{}).get('visibility_edges',[])),room_type_hints=list(bundle['graph'].get('vsm',{}).get('room_type_index',{})),all_reference_files=len(refs),inspection=checked,scope='Cold public reader reads all views/RGB/depth, tiles and object identities from final root only')
    finally:reader.close()

def confine_read(allowed):
    if platform.system()!='Linux'or platform.machine()not in('x86_64','aarch64'):raise RuntimeError('Unsupported Landlock reader platform')
    class Ruleset(ctypes.Structure):_fields_=[('handled_access_fs',ctypes.c_uint64)]
    class Beneath(ctypes.Structure):_pack_=1;_fields_=[('allowed_access',ctypes.c_uint64),('parent_fd',ctypes.c_int32)]
    bits=(1<<0)|(1<<2)|(1<<3);libc=ctypes.CDLL(None,use_errno=True);abi=libc.syscall(444,0,0,1)
    if abi<3:raise RuntimeError('Landlock ABI>=3 required; no unconfined fallback')
    rules=Ruleset(bits);fd=libc.syscall(444,ctypes.byref(rules),ctypes.sizeof(rules),0)
    if fd<0:raise OSError(ctypes.get_errno(),'create reader ruleset')
    try:
        for item in sorted({str(Path(p).resolve())for p in allowed if Path(p).exists()}):
            path=Path(item);pfd=os.open(path,getattr(os,'O_PATH',0o10000000)|os.O_CLOEXEC)
            try:
                rule=Beneath(bits if path.is_dir()else bits&~(1<<3),pfd)
                if libc.syscall(445,fd,1,ctypes.byref(rule),0)<0:raise OSError(ctypes.get_errno(),'add reader rule '+item)
            finally:os.close(pfd)
        if libc.prctl(38,1,0,0,0)!=0:raise OSError(ctypes.get_errno(),'reader no-new-privileges')
        if libc.syscall(446,fd,0)<0:raise OSError(ctypes.get_errno(),'restrict reader')
    finally:os.close(fd)
    return int(abi)

def retain_final_map(memory,work,result,identity,*,max_compressed=8*1024**3,max_expanded=8*1024**3):
    memory=Path(memory).resolve();work=Path(work).resolve();result=Path(result).resolve();case=PROJECT_ROOT
    if not work.is_relative_to(case/'outputs/graph_memory')or not result.is_relative_to(case/'outputs/graph_memory'):raise ValueError('Final-map transaction must stay in owned graph output')
    if not memory.is_relative_to(work):raise ValueError('Original map must be in this newly gathered episode work')
    scope=json.loads((memory/'episode_scope.json').read_bytes())
    if scope['member']!=identity['member']or scope['attempt_id']!=identity['attempt']:raise ValueError('Final map belongs to another member/attempt')
    expected=json.loads((result/'production_scope.json').read_bytes())['scope']
    if canonical(scope)!=canonical(expected):raise ValueError('Final map scope differs from actual registered production scope')
    if not(memory/'CURRENT.json').is_file():raise ValueError('No committed snapshot to retain')
    work.mkdir(exist_ok=True,parents=True);result.mkdir(exist_ok=True,parents=True)
    if (result/'final-map.tar.gz').exists()or(result/'final-map.json').exists():raise FileExistsError('Never replace an existing final map receipt')
    temporary=work/('final-retention-'+uuid.uuid4().hex);temporary.mkdir(exist_ok=False);marker=dict(transaction=temporary.name,identity=identity)
    atomic_json(temporary/'OWNER.json',marker)
    final=temporary/'map';export=export_final(memory,final);render=render_episode(final,out=final/'browser',export_object_cloud=False);verify_final(final)
    package=pack_tree(final,result/'final-map.tar.gz',max_bytes=max_compressed)
    if package['expanded_bytes']>max_expanded:raise ValueError('Final map exceeds declared restore bound')
    cold=temporary/'cold';unpack_tree(result/'final-map.tar.gz',cold,max_expanded=max_expanded,expected_sha256=package['sha256'])
    cold_receipt=result/'final-map-cold-read.json'
    protection=json.loads(os.environ.get('CASE1_PROTECTION','{}'))
    if protection.get('landlock_abi',0)<3:raise RuntimeError('Cold child requires actual inherited with_runtime protection')
    command=[sys.executable,'-B','-m','graphAdapter.map_memory.storage.final_snapshot','cold-verify','--root',str(cold),'--receipt',str(cold_receipt),'--forbidden',str(memory/'CURRENT.json')]
    with(result/'final-map-cold-read.log').open('x')as log:
        done=subprocess.run(command,cwd=case,stdout=log,stderr=subprocess.STDOUT)
    if done.returncode:raise RuntimeError('Final map cold load failed; all original and temporary material retained')
    checked=json.loads(cold_receipt.read_bytes())
    if checked.get('status')!='VERIFIED'or checked.get('source_read_blocked')is not True or checked['snapshot_id']!=export['final_snapshot_id']:raise ValueError('Cold final map identity or confinement mismatch')
    before=footprint(temporary)
    receipt=dict(schema='retained_final_map_v1',identity=identity,source_snapshot_id=export['source_snapshot_id'],final_snapshot_id=export['final_snapshot_id'],package=package,logical_hashes=export['logical_hashes'],cold_read=checked,cold_read_sha256=sha(cold_receipt),render=render,
        temporary_peak_observed=before,source_footprint=export['source_footprint'],status='VERIFIED_FINAL_MAP_BEFORE_COMPUTE_RELEASE',scope='Final map and all referenced RGB-D/object/tile/anchor material retained; native and intermediate versions remain governed separately')
    atomic_json(result/'final-map.json',receipt)
    assert_no_open_files(temporary)
    if not temporary.resolve().is_relative_to(work)or json.loads((temporary/'OWNER.json').read_bytes())!=marker:raise ValueError('Temporary owner mismatch; no cleanup')
    shutil.rmtree(temporary)
    atomic_json(result/'final-map-temporary-release.json',dict(identity=identity,transaction=marker['transaction'],cold_read_sha256=sha(cold_receipt),original_map_untouched=True,released_bytes=before['allocated_bytes']))
    return receipt

def cold_verify(root,receipt,forbidden):
    root=Path(root).resolve();receipt=Path(receipt).absolute();forbidden=Path(forbidden).resolve();case=PROJECT_ROOT
    if root==forbidden or forbidden.is_relative_to(root):raise ValueError('Negative target must be outside final map')
    abi=confine_read([root,case/'runtime/awarevln',case/'runtime/graph_memory/perception',case/'runtime/graph_memory/borrowed_base',case/'runtime/graph_memory/package_root',case/'src/graphAdapter',Path(__file__),'/usr','/lib','/lib64','/bin','/etc/ld.so.cache','/etc/ld.so.conf','/etc/ld.so.conf.d','/dev','/proc'])
    try:
        with forbidden.open('rb')as f:f.read(1)
    except PermissionError:blocked=True
    else:raise RuntimeError('Original source readable; reject cold audit')
    protection=json.loads(os.environ.get('CASE1_PROTECTION','{}'))
    if protection.get('landlock_abi',0)<3:raise RuntimeError('Missing inherited runtime protection')
    result=verify_final(root);result.update(inherited_runtime_protection=protection,read_landlock_abi=abi,source_read_blocked=blocked)
    with receipt.open('x')as f:json.dump(result,f,indent=2);f.flush();os.fsync(f.fileno())
    return result

def verify_retained_final_map(result,receipt,identity):
    result=Path(result);declared=receipt.get('qualification',{}).get('final_map')
    if not isinstance(declared,dict):raise ValueError('Final-map qualification missing; original work preserved')
    actual=json.loads((result/'final-map.json').read_bytes())
    if actual!=declared or actual.get('identity')!=identity:raise ValueError('Final-map declaration identity mismatch')
    if declared.get('status')=='NO_COMMITTED_MAP':
        if receipt['summary'].get('status')!='failed'or receipt['summary'].get('map_memory',{}).get('snapshot_id'):raise ValueError('Committed maps cannot be relabeled missing')
        return True
    if actual!=declared or actual['identity']!=identity or actual['status']!='VERIFIED_FINAL_MAP_BEFORE_COMPUTE_RELEASE':raise ValueError('Final-map identity/qualification mismatch')
    cold=json.loads((result/'final-map-cold-read.json').read_bytes())
    if cold!=actual['cold_read']or cold.get('source_read_blocked')is not True or sha(result/'final-map-cold-read.json')!=actual['cold_read_sha256']:raise ValueError('Final-map cold receipt mismatch')
    if sha(result/'final-map.tar.gz')!=actual['package']['sha256']:raise ValueError('Final-map package changed')
    return True

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('op',choices=['verify','cold-verify']);p.add_argument('--root',required=True);p.add_argument('--receipt');p.add_argument('--forbidden');a=p.parse_args()
    result=cold_verify(a.root,a.receipt,a.forbidden)if a.op=='cold-verify'else verify_final(a.root)
    print(json.dumps(result,indent=2))
