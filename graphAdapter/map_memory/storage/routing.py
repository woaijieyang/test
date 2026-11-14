"""Creation-time ownership and production episode routing.

Only fresh scopes registered by a producer are gathered. Sensory inputs, host
evaluation traces and private map outputs remain separate while workers run.
"""
from pathlib import Path
from contextlib import contextmanager
import fcntl,json,os,uuid,hashlib
from .lifecycle import (EpisodeLifecycle,EpisodeSession,LifecycleError,canonical,json_rows,
    atomic_json,immutable_json,inside,segment,sha,process_identity,
    assert_no_open_files,verify_close_acknowledgement)

ROOT=Path(__file__).resolve().parents[4]
MARKER=".producer-owner.json"

def roles_for(episode):
    return episode.entry.get("owner_roles_by_side",{}).get(episode.side,episode.plan["owner_roles"])

@contextmanager
def route_lock(path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("a+b")as stream:
        fcntl.flock(stream,fcntl.LOCK_EX)
        yield

def from_environment():
    raw=os.environ.get("CASE2_STORAGE_BINDING")
    return RunRouting(json.loads(raw))if raw else None

def create_run(root,plan,*,run_uid=None):
    digest=EpisodeLifecycle.create_run(root,plan)
    run_uid=segment(run_uid or("storage-"+uuid.uuid4().hex))
    atomic_json(Path(root)/"routing_run.json",dict(run_uid=run_uid,plan_sha256=digest,
        creator=process_identity(os.getpid()),schema_version=1))
    return dict(root=str(Path(root).absolute()),plan_sha256=digest)

class RunRouting:
    def __init__(self,binding):
        self.root=Path(binding["root"]).absolute()
        self.plan_sha=binding["plan_sha256"]
        if sha(self.root/"retention_plan.json")!=self.plan_sha:raise LifecycleError("Routing plan changed")
        self.plan=json.loads((self.root/"retention_plan.json").read_bytes())
        self.run=json.loads((self.root/"routing_run.json").read_bytes())
        if self.run["plan_sha256"]!=self.plan_sha:raise LifecycleError("Routing run identity")
        self.side=segment(binding["side"]);self.attempt=segment(binding["attempt"])
        self.worker=segment(binding.get("worker_id","worker0"))
        if self.side not in("control","shadow"):raise LifecycleError("Routing side")
        self.sessions={}

    def episode(self,scope):
        member=list(scope["member"])
        entry=next((row for row in self.plan["entries"]if row["member"]==member),None)
        if entry is None:raise LifecycleError("Episode not in presealed routing plan")
        ep=EpisodeLifecycle(self.root,entry["key"],self.side,self.attempt,plan_sha256=self.plan_sha)
        with route_lock(self.root/"control"/(entry["key"]+"-"+self.side+"-"+self.attempt+".lock")):
            if not ep.result.exists():
                stop=self.root/'control/STOP_NEW_EPISODES.json'
                if stop.exists():raise LifecycleError('Run controller stopped new episodes for capacity;failure retained')
                capacity=self.plan.get('capacity_admission',{})
                fs=os.statvfs(self.root);free=fs.f_bavail*fs.f_frsize
                threshold=capacity.get('emergency_bytes',0)+capacity.get('active_workers',1)*capacity.get('new_episode_margin_bytes',0)
                if free<threshold:raise LifecycleError('Capacity admission stopped new episode;no synthetic STOP')
                ep.create_work()
            elif ep._state()["state"]!="ACTIVE":raise LifecycleError("Episode routing already frozen")
            ep._owned()
            identity=ep.result/"production_scope.json"
            expected=dict(scope=scope,binding=dict(side=self.side,attempt=self.attempt,worker_id=self.worker))
            immutable_json(identity,expected)
        return ep

    def _routes(self,ep):
        path=ep.result/"routes.json"
        return json.loads(path.read_bytes())if path.exists()else dict(identity=ep.identity,scopes=[],closed={})

    def register(self,ep,role,path,target):
        role=segment(role);path=Path(path).absolute()
        if role not in roles_for(ep):raise LifecycleError("Unregistered producer role")
        target=Path(target)
        if target.is_absolute()or ".."in target.parts:raise LifecycleError("Unsafe gather target")
        allowed=(self.root,ROOT/"runtime/pose/sessions"/self.run["run_uid"],
                 ROOT/"logs/pose"/self.run["run_uid"])
        base=next((base for base in allowed if base in path.parents),None)
        if base is None:raise LifecycleError("Producer scope outside this new run")
        inside(ROOT,path)
        with route_lock(ep.result/"routes.lock"):
            routes=self._routes(ep)
            if routes["identity"]!=ep.identity:raise LifecycleError("Routing identity")
            old=next((x for x in routes["scopes"]if x["path"]==str(path)),None)
            if old:
                self.verify_scope(ep,old)
                if old["role"]!=role or old["target"]!=str(target):raise LifecycleError("Scope rebound")
                return path
            if any(x["target"]==str(target)for x in routes["scopes"]):raise LifecycleError("Gather target reused")
            if path.exists():raise LifecycleError("Cannot adopt preexisting producer directory")
            nonce=uuid.uuid4().hex
            row=dict(role=role,path=str(path),target=str(target),nonce=nonce,
                creator=process_identity(os.getpid()),state="RESERVED")
            routes["scopes"].append(row);atomic_json(ep.result/"routes.json",routes)
            path.mkdir(parents=True,exist_ok=False)
            atomic_json(path/MARKER,dict(identity=ep.identity,role=role,nonce=nonce))
            st=path.stat();row.update(state="OPEN",device=st.st_dev,inode=st.st_ino)
            atomic_json(ep.result/"routes.json",routes)
        return path

    def verify_scope(self,ep,row):
        path=Path(row["path"])if row["state"]!="GATHERED"else ep.work/row["target"]
        inside(ROOT,path)
        moved=ep.work/row['target']
        if not path.exists()and moved.exists():
            path=moved
            row['state']='GATHERED'
        marker=json.loads((path/MARKER).read_bytes())
        if marker!=dict(identity=ep.identity,role=row["role"],nonce=row["nonce"]):
            raise LifecycleError("Producer ownership marker changed")
        st=path.stat()
        if (st.st_dev,st.st_ino)!=(row["device"],row["inode"]):raise LifecycleError("Producer inode changed")
        return path

    def session(self,ep,role):
        key=(ep.key,role)
        if key not in self.sessions:self.sessions[key]=EpisodeSession(ep,role)
        return self.sessions[key]

    def accept(self,ep,role,ack):
        ticket=json.loads((ep.result/"owner_sessions"/(role+".json")).read_bytes())
        verify_close_acknowledgement(ticket,ack,ep.plan["owner_components"][role])
        with route_lock(ep.result/"routes.lock"):
            routes=self._routes(ep)
            if role in routes["closed"]:
                if routes["closed"][role]!=ack:raise LifecycleError("Close receipt changed")
            else:
                routes["closed"][role]=ack;atomic_json(ep.result/"routes.json",routes)
        return self.try_finalize(ep)

    def native_namespace(self,ep,episode_uid):
        prefix=self.run["run_uid"]+"/"+segment(episode_uid)
        self.register(ep,"pose",ROOT/"runtime/pose/sessions"/prefix,"native")
        self.register(ep,"pose",ROOT/"logs/pose"/prefix,"pose_logs")
        return prefix

    def close_files(self,ep,role,handles):
        ack=self.session(ep,role).close_files(handles)
        return self.accept(ep,role,ack)

    def close_host(self,ep,recorder):
        ack=self.session(ep,"host").close_trace(recorder)
        return self.accept(ep,"host",ack)

    def close_pose(self,ep,bridge):
        owner=self.session(ep,"pose")
        ack=(owner.close_pose_provider(bridge) if getattr(bridge,'pose_provider',None)=='simulator_ground_truth'
             else owner.close_pose(bridge))
        return self.accept(ep,"pose",ack)

    def try_finalize(self,ep):
        with route_lock(ep.result/"finalize-route.lock"):
            if ep._state()["state"]=="DELETED":
                return dict(state="DELETED",result=str(ep.result))
            if ep._state()['state']in('SEALED','DELETING'):
                from graphAdapter.evaluation.runner import finalize_retained_episode
                return dict(state='DELETED',result=str(ep.result),outcome=finalize_retained_episode(ep,{}))
            routes=self._routes(ep)
            expected=set(roles_for(ep))
            if set(routes["closed"])!=expected:
                return dict(state="WAITING",missing_roles=sorted(expected-set(routes["closed"])))
            for row in routes["scopes"]:
                path=self.verify_scope(ep,row)
                assert_no_open_files(path)
            atomic_json(ep.result/'routes.json',routes)
            # Scoped moves affect only freshly created dirs within case2. Sources
            # are never removed before their producer's typed close acknowledgement.
            for row in routes["scopes"]:
                if row["state"]=="GATHERED":continue
                path=self.verify_scope(ep,row);target=ep.work/row["target"]
                inside(ep.work,target)
                if path.stat().st_dev!=ep.work.stat().st_dev:
                    raise LifecycleError("Cross-device gathering requires explicit copy/peak admission")
                target.parent.mkdir(parents=True,exist_ok=True)
                if target.exists():raise LifecycleError("Gather destination already exists")
                os.rename(path,target)
                row["state"]="GATHERED";atomic_json(ep.result/"routes.json",routes)
            host=next(x for x in routes["scopes"]if x["role"]=="host")
            host_root=ep.work/host["target"];trace=host_root/"trace.jsonl"
            result_path=host_root/"result.json"
            summary=json.loads(result_path.read_bytes())if result_path.exists()else dict(status='failed',fixed_denominator=1,episode_sequence=next(json_rows(trace)).get('episode_sequence'),trace_sha256=sha(trace),metrics=None,termination_reason='owner_exited')
            streams={};memory=None
            source=next((x for x in routes["scopes"]if x["role"]=="source000"),None)
            if source:
                source_root=ep.work/source["target"]
                streams=dict(observation_packets=source_root/"observation-packets.jsonl",flow=source_root/"flow_trace.jsonl")
            mem=next((x for x in routes["scopes"]if x["role"]=="memory"),None)
            if mem:
                memory=ep.work/mem["target"]/"attempt_000"
                commits=memory/'execution.jsonl'
                if not commits.exists():commits.write_text('')
                streams['map_commits']=commits
                if(memory/'CURRENT.json').exists():
                    from graphAdapter.evaluation.retained import audit_memory_materials
                    history=ep.work/('memory-history-'+uuid.uuid4().hex+'.jsonl')
                    summary['memory_material_audit']=audit_memory_materials(memory,streams['observation_packets'],streams['flow'],history,
                        required_sampling=self.plan.get('production_schema')=='release4_endpoint_v1',
                        frozen_source_sha256=self.plan.get('evidence_source_sha256'))
                    streams['memory_history']=history
                elif summary.get('status')=='failed':summary['memory_material_audit']=dict(status='FAILED_NO_PUBLICATION',frames=0)
                else:raise LifecycleError('Successful episode has no published map')
                if(memory/'episode_summary.json').exists():summary['map_memory']=json.loads((memory/'episode_summary.json').read_bytes())
            mode=ep.entry.get('mode_by_side',{}).get(ep.side,ep.entry['mode'])
            preview=None
            if mode=='preview_only':
                if memory is None:raise LifecycleError('Preview needs actual memory snapshot')
                from graphAdapter.map_memory.visualization import render_episode
                rendered=render_episode(memory,out=ep.work/'preview',height_slice='auto')
                candidates=list((ep.work/'preview').glob('*.png'))
                if not candidates:raise LifecycleError('Renderer produced no preview')
                preview=candidates[0]
            if mode=='audit_full':
                if source is None or memory is None:raise LifecycleError('Full audit roles incomplete')
                locator={}
                for packet in json_rows(streams['observation_packets']):
                    for key in('raw_rgb_ref','raw_depth_ref','aligned_ref'):
                        ref=packet.get(key)
                        if ref is not None:
                            path=source_root/Path(ref).parent.name/Path(ref).name
                            locator[ref]=dict(codec='npy',path=str(path.relative_to(ep.work)))
                atomic_json(ep.work/'source-locators.json',locator)
                dbs=list((ep.work/'native').glob('*/map.db'))
                if len(dbs)!=1:raise LifecycleError('Unique native database required')
                import shutil
                source_lock=self.root/'control/source-freeze.json';source_archive=self.root/'control/source.tar.gz'
                config=self.root/'control/effective-profile.json'
                for file in(source_lock,source_archive,config):
                    if not file.is_file():raise LifecycleError('Frozen source/config needed for audit_full')
                    shutil.copyfile(file,ep.work/file.name)
                refs=dict(host_trace=trace,source_packets=streams['observation_packets'],flow_trace=streams['flow'],
                    source_locator_map=ep.work/'source-locators.json',calibration=source_root/'calibration.json',
                    native_db=dbs[0],source_lock=ep.work/'source-freeze.json',source_archive=ep.work/'source.tar.gz',
                    effective_config=ep.work/'effective-profile.json')
                atomic_json(ep.work/'audit_inputs.json',{key:dict(path=str(value.relative_to(ep.work)),sha256=sha(value))for key,value in refs.items()})
            release=dict(consumers_joined=True,native_closed=True,memory_closed=True,pins=0,leases=0,
                owners=[],cache_entries={role:0 for role in expected},session_receipts=routes["closed"],
                scope="Registered production callbacks;shared processes may remain;not kernel quota")
            from graphAdapter.evaluation.runner import finalize_retained_episode
            request=dict(trace=trace,image_root=ep.work,summary=summary,release=release,
                memory=memory,preview=preview,evidence_streams=streams)
            outcome=finalize_retained_episode(ep,request)
            return dict(state="DELETED",result=str(ep.result),outcome=outcome)

def load_run(path):
    path=Path(path).absolute()
    if path.name!="routing_run.json":raise LifecycleError("Fixed routing manifest name required")
    inside(ROOT/"outputs/graph_memory",path)
    value=json.loads(path.read_bytes())
    root=path.parent
    if sha(root/"retention_plan.json")!=value["plan_sha256"]:raise LifecycleError("Run plan drift")
    return root,value

def create_process_scope(root,path,kind,*,defer_marker=False):
    root=Path(root).absolute();run=json.loads((root/"routing_run.json").read_bytes())
    path=Path(path).absolute();inside(ROOT,path);segment(kind)
    allowed=(root,ROOT/"runtime/pose/brokers",ROOT/"runtime/graph_memory/brokers",
             ROOT/"runtime/graph_memory/sessions"/run["run_uid"])
    if not any(base in path.parents for base in allowed):raise LifecycleError("Process scope outside registered run")
    with route_lock(root/"control/process-scopes.lock"):
        registry=root/"control/process-scopes.json"
        data=json.loads(registry.read_bytes())if registry.exists()else[]
        if path.exists():raise LifecycleError("Cannot adopt old process directory")
        nonce=uuid.uuid4().hex
        record=dict(path=str(path),kind=kind,run_uid=run["run_uid"],nonce=nonce,
                    creator=process_identity(os.getpid()),owner=None,closed=False)
        data.append(record);atomic_json(registry,data)
        path.mkdir(parents=True,exist_ok=False)
        if not defer_marker:atomic_json(path/MARKER,dict(run_uid=run["run_uid"],kind=kind,nonce=nonce))
        st=path.stat();record.update(device=st.st_dev,inode=st.st_ino)
        atomic_json(registry,data)
    return path

def bind_process_scope(root,path,owner):
    root=Path(root).absolute();path=Path(path)
    with route_lock(root/"control/process-scopes.lock"):
        registry=root/"control/process-scopes.json";data=json.loads(registry.read_bytes())
        row=next(x for x in data if x["path"]==str(path))
        if process_identity(owner["pid"])!=owner:raise LifecycleError("Process owner identity mismatch")
        if(path.stat().st_dev,path.stat().st_ino)!=(row["device"],row["inode"]):raise LifecycleError("Process scope inode changed")
        marker=dict(run_uid=row["run_uid"],kind=row["kind"],nonce=row["nonce"])
        if(path/MARKER).exists():
            if json.loads((path/MARKER).read_bytes())!=marker:raise LifecycleError("Process marker changed")
        else:atomic_json(path/MARKER,marker)
        row["owner"]=owner;atomic_json(registry,data)

def process_scope_closed(root,path,*,outcome):
    root=Path(root).absolute()
    with route_lock(root/"control/process-scopes.lock"):
        registry=root/"control/process-scopes.json";data=json.loads(registry.read_bytes())
        row=next(x for x in data if x["path"]==str(path))
        owner=row.get("owner")
        if owner is None or process_identity(owner["pid"])==owner:raise LifecycleError("Process scope owner still alive/unknown")
        row.update(closed=True,outcome=outcome);atomic_json(registry,data)

def release_process_scopes(root):
    """After registered owners exit,remove only known tmp/cache;keep bounded receipts/logs."""
    from .lifecycle import compress_jsonl,usage,sync_dir
    root=Path(root).absolute();released=[];pending=[]
    registry=root/"control/process-scopes.json"
    if not registry.exists():return dict(released=[],pending=[])
    with route_lock(root/"control/process-scopes.lock"):
        data=json.loads(registry.read_bytes())
        for row in sorted(data,key=lambda item:len(Path(item['path']).parts),reverse=True):
            if row.get("released"):continue
            owner=row.get("owner")
            if owner is None or owner_still_running(owner):
                pending.append(row["path"]);continue
            path=Path(row["path"]);inside(ROOT,path)
            if any(other is not row and path in Path(other['path']).parents and owner_still_running(other.get('owner'))for other in data):
                pending.append(row['path']);continue
            archive=root/'process-receipts'/(row['nonce']+'.tar.gz')
            if not path.exists():
                inherited_member=None
                if not archive.is_file():
                    import tarfile
                    for parent in data:
                        parent_path=Path(parent['path'])
                        parent_archive=root/'process-receipts'/(parent['nonce']+'.tar.gz')
                        if parent_path not in path.parents or not parent_archive.exists():continue
                        prefix=str(path.relative_to(parent_path));member=prefix+'/'+MARKER
                        with tarfile.open(parent_archive,'r:gz')as stored:
                            try:marker=json.loads(stored.extractfile(member).read())
                            except KeyError:continue
                        if marker==dict(run_uid=row['run_uid'],kind=row['kind'],nonce=row['nonce']):
                            archive=parent_archive;inherited_member=member;break
                    if not archive.is_file():raise LifecycleError('Process directory missing without retained package')
                import tarfile
                with tarfile.open(archive,'r:gz')as saved:
                    marker=json.loads(saved.extractfile(inherited_member or MARKER).read())
                    if marker!=dict(run_uid=row['run_uid'],kind=row['kind'],nonce=row['nonce']):
                        raise LifecycleError('Recovered process package identity mismatch')
                    for member in saved:
                        if not member.isfile():raise LifecycleError('Recovered package contains nonregular member')
                        stream=saved.extractfile(member)
                        for block in iter(lambda:stream.read(1024**2),b''):pass
                row.update(released=True,closed=True,recovered_cleanup=True,
                    retained_package=dict(sha256=sha(archive),compressed_bytes=archive.stat().st_size,archive_path=str(archive),inherited_member=inherited_member))
                atomic_json(registry,data);released.append(row['path']);continue
            if json.loads((path/MARKER).read_bytes())!=dict(run_uid=row["run_uid"],kind=row["kind"],nonce=row["nonce"]):
                raise LifecycleError("Process cleanup marker changed")
            if(path.stat().st_dev,path.stat().st_ino)!=(row["device"],row["inode"]):
                raise LifecycleError("Process cleanup inode changed")
            # A host output or map output may still contain unfinalized episodes.
            # It is retained rather than silently swallowing failure evidence.
            if row['kind']in('host_output','memory_output'):
                unfinalized=False
                for registry_path in(root/'results').glob('*/*/*/routes.json'):
                    ep_state=json.loads((registry_path.parent/'state.json').read_bytes())['state']
                    scopes=json.loads(registry_path.read_bytes())['scopes']
                    if ep_state!='DELETED'and any(path==Path(scope['path'])or path in Path(scope['path']).parents for scope in scopes):
                        unfinalized=True;break
                if unfinalized:pending.append(row['path']);continue
            assert_no_open_files(path)
            if row['kind']in('pose_broker','memory_broker'):
                import stat
                endpoint=path/'broker.sock'
                if endpoint.exists():
                    if not stat.S_ISSOCK(endpoint.lstat().st_mode):raise LifecycleError('Broker endpoint type changed')
                    endpoint.unlink();row['closed_unix_endpoint_removed']=True
            before=usage(path)
            from .lifecycle import regular_tree
            cache_released=0
            for name in('tmp','cache'):
                temporary=path/name
                if not temporary.exists():continue
                for item in list(regular_tree(temporary)):
                    cache_released+=item.stat().st_size;item.unlink()
                for directory in sorted((p for p in temporary.rglob('*')if p.is_dir()),key=lambda p:len(p.parts),reverse=True):directory.rmdir()
                temporary.rmdir()
            # Preserve every metadata/log byte in a lossless bounded package.
            archive=root/"process-receipts"/(row["nonce"]+".tar.gz")
            archive.parent.mkdir(exist_ok=True)
            from .lifecycle import pack_tree,regular_tree
            package=pack_tree(path,archive,max_bytes=64*1024**2)
            row.update(cleanup_state='ARCHIVED',retained_package=package,original_bytes=before,
                reconstructible_cache_released_bytes=cache_released)
            atomic_json(registry,data)
            keep=set()
            if row['kind']=='host_output':
                keep={MARKER,'effective-config.yaml','model-receipt.json','hook-load.json','launch-binding.json',
                    'host-transform.json','worker-done.json','launch-config.yaml','results.jsonl'}
            for item in list(regular_tree(path)):
                if str(item.relative_to(path))not in keep:item.unlink()
            for directory in sorted((p for p in path.rglob('*')if p.is_dir()),key=lambda p:len(p.parts),reverse=True):
                if not any(directory.iterdir()):directory.rmdir()
            if not keep:path.rmdir()
            sync_dir(path.parent)
            row.update(released=True,closed=True,retained_package=package,original_bytes=before,
                reconstructible_cache_released_bytes=cache_released,
                retained_light_metadata=usage(path)if keep else None)
            atomic_json(registry,data)
            released.append(row["path"])
        atomic_json(registry,data)
    return dict(released=released,pending=pending)

def owner_still_running(owner):
    if owner is None or process_identity(owner["pid"])!=owner:return False
    try:state=Path("/proc/"+str(owner["pid"])+"/stat").read_text().rsplit(")",1)[1].split()[0]
    except FileNotFoundError:return False
    return state not in("Z","X")

def recover_failed_episode(route,ep):
    """Revoke crashed producer sessions only after all registered processes exit.

    Recovery is explicitly abnormal. It never claims graceful DB/model closure
    or rewrites a trace. Unparseable evidence stays owned and uncollected.
    """
    import hmac
    with route_lock(ep.result/"routes.lock"):
        routes=route._routes(ep)
        for row in routes["scopes"]:
            if owner_still_running(row["creator"]):raise LifecycleError("Episode creator is still running")
        processes=[]
        registry=route.root/"control/process-scopes.json"
        if registry.exists():
            for row in json.loads(registry.read_bytes()):
                if row["kind"]=="memory_output"and any(Path(row["path"])in Path(s["path"]).parents for s in routes["scopes"]):
                    processes.append(row.get("owner"))
        for row in routes["scopes"]:
            if row["role"]=="pose":
                for record in Path(row["path"]).rglob("process.json"):
                    payload=json.loads(record.read_bytes())
                    processes.append(dict(pid=payload["pid"],starttime=payload["starttime"]))
        if any(owner_still_running(owner)for owner in processes):raise LifecycleError("A registered private/native process remains")
        for role in roles_for(ep):
            if role in routes["closed"]:continue
            ticket_path=ep.result/"owner_sessions"/(role+".json")
            if not ticket_path.exists():raise LifecycleError("Missing creation ticket;cannot fabricate recovery")
            ticket=json.loads(ticket_path.read_bytes())
            with (ticket_path.parent/(role+".lock")).open("a+b")as guard:
                try:fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError as error:raise LifecycleError("Live producer capability")from error
                observed=dict(component=ep.plan["owner_components"][role],recovered_after_process_exit=True,
                    graceful_close=False,known_processes=processes)
                if "expected_store_root"in ticket:
                    observed.update(root=ticket["expected_store_root"],episode_uid=ticket["expected_episode_uid"])
                payload=dict(identity=ep.identity,role=role,process=ticket["process"],nonce=ticket["nonce"],
                             session_revoked=True,observed=observed)
                ack=dict(payload=payload,signature=hmac.new(bytes.fromhex(ticket["key"]),canonical(payload),hashlib.sha256).hexdigest())
                routes["closed"][role]=ack
        atomic_json(ep.result/"routes.json",routes)
        atomic_json(ep.result/"failure-owner-recovery.json",dict(identity=ep.identity,
            failed=True,trace_rewritten=False,graceful_close_claim=False,registered_processes=processes))
    return route.try_finalize(ep)


def prepare_production_run(root,plan,profile_path):
    """Freeze live source/config before producers start;does not authorize navigation."""
    import tarfile,shutil
    from graphAdapter.evaluation.registry_binding import source_snapshot
    files,source=source_snapshot(ROOT,map_stage=True)
    profile=json.loads(Path(profile_path).read_bytes())
    if profile.get('feature')!='map_memory':raise LifecycleError('001 map profile required')
    plan=dict(plan,evidence_source_sha256=source)
    binding=create_run(root,plan)
    root=Path(binding['root']);control=root/'control';control.mkdir(exist_ok=True)
    atomic_json(control/'source-freeze.json',dict(source_sha256=source,files=files))
    with tarfile.open(control/'source.tar.gz','w:gz')as archive:
        for row in files:archive.add(row['path'],arcname=str(Path(row['path']).relative_to(ROOT)),recursive=False)
    shutil.copyfile(profile_path,control/'effective-profile.json')
    policy=Path(profile['acceptance_policy'])
    if sha(policy)!=profile['acceptance_policy_sha256']:raise LifecycleError('Frozen acceptance policy differs')
    shutil.copyfile(policy,control/'acceptance_policy.json')
    profile=dict(profile)
    profile['storage_lifecycle']=dict(profile.get('storage_lifecycle',{}),routing=binding)
    profile['map_memory']=dict(profile['map_memory'],routed_storage=True)
    # Keep every existing implementation/fullA gate;preparation is not acceptance.
    atomic_json(control/'routed-profile.json',profile)
    return dict(binding=binding,source_sha256=source,profile=str(control/'routed-profile.json'),navigation_authorized=False)
