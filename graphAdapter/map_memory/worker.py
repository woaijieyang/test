"""Fixed private memory worker launcher, JSON RPC and lightweight host client.

Broker runs before host write confinement. It accepts owned paths,not executables,
environment overrides,models or arbitrary PIDs. Heavy imports occur only in worker.
"""
from pathlib import Path
import argparse,ctypes,json,os,signal,socket,struct,subprocess,sys,threading,time,uuid
ROOT=Path(__file__).resolve().parents[3]
MAX_MESSAGE=32*1024*1024
_FROZEN_UNSET=object()

class MemoryTransportError(OSError):
    """RPC framing/connection can no longer be safely reused."""
    pass

def validate_prepared_commit(result,target_version,packet):
    versions=result.get("versions") if isinstance(result,dict) else None
    cutoff=result.get("cutoff") if isinstance(result,dict) else None
    if not isinstance(versions,dict) or "pose_map_version" not in versions or versions["pose_map_version"]!=target_version or type(versions["pose_map_version"])is not type(target_version):
        raise RuntimeError("Commit reply differs from the prepared pose version")
    if (not isinstance(cutoff,dict) or type(cutoff.get("capture_seq"))is not int
            or type(cutoff.get("event_seq"))is not int or cutoff["capture_seq"]!=packet.capture_seq
            or cutoff["event_seq"]!=packet.event_seq):
        raise RuntimeError("Commit reply differs from the prepared observation cutoff")
    return result

def send(sock,value):
    data=json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(",",":")).encode()
    if len(data)>MAX_MESSAGE:raise ValueError("Memory RPC payload budget exceeded")
    sock.sendall(struct.pack("!I",len(data))+data)
def _exact(sock,n):
    output=bytearray()
    while len(output)<n:
        block=sock.recv(n-len(output))
        if not block:raise EOFError("Memory worker channel closed")
        output.extend(block)
    return bytes(output)
def receive(sock):
    size=struct.unpack("!I",_exact(sock,4))[0]
    if size>MAX_MESSAGE:raise ValueError("Memory RPC incoming budget exceeded")
    return json.loads(_exact(sock,size))

def owned_path(value,base,*,must_exist=False):
    p=Path(value)
    if not p.is_absolute()or not p.resolve().is_relative_to(base.resolve()):raise ValueError("Path outside owned memory scope")
    for item in (p,*p.parents):
        if item==ROOT.parent:break
        if item.is_symlink():raise ValueError("Private path contains symlink")
    if must_exist and not p.is_dir():raise ValueError("Private directory missing")
    return p

def isolated_command(session,source_root,output_root):
    import shutil
    session=owned_path(session,ROOT/"runtime/graph_memory/sessions",must_exist=True)
    source_root=owned_path(source_root,ROOT/"outputs/graph_memory",must_exist=True)
    output_root=owned_path(output_root,ROOT/"outputs/graph_memory",must_exist=True)
    if output_root.resolve()==(ROOT/"outputs/graph_memory").resolve()or any(output_root.iterdir()):
        raise ValueError("Memory output mount must be a new empty attempt directory")
    if source_root.resolve().is_relative_to(output_root.resolve())or session.resolve().is_relative_to(output_root.resolve()):
        raise ValueError("Memory output cannot contain source or session inputs")
    if source_root.name!="observation_pose"or "evaluation_private"in source_root.parts or "evaluation_private"in output_root.parts:
        raise ValueError("Only declared RGB-D source/archive output scopes may be mounted")
    executable=shutil.which("bwrap")
    if not executable:raise RuntimeError("Memory worker requires bwrap;no unisolated fallback")
    command=[executable,"--unshare-pid","--unshare-net","--unshare-ipc","--die-with-parent","--ro-bind","/usr","/usr"]
    for name in ("lib","lib64","bin","sbin"):
        p=Path("/")/name
        if p.is_symlink():command+=["--symlink",os.readlink(p),str(p)]
        elif p.exists():command+=["--ro-bind",str(p),str(p)]
    for value in ("/etc/ld.so.cache","/etc/ld.so.conf","/etc/ld.so.conf.d"):
        if Path(value).exists():command+=["--ro-bind",value,value]
    command+=["--proc","/proc","--dev-bind","/dev","/dev","--ro-bind","/sys","/sys","--tmpfs","/tmp","--tmpfs","/home"]
    if Path("/proc/driver/nvidia").exists():command+=["--ro-bind","/proc/driver/nvidia","/proc/driver/nvidia"]
    readonly=("runtime/awarevln","runtime/graph_memory/perception","runtime/graph_memory/borrowed_base",
        "runtime/graph_memory/package_root","runtime/graph_memory/model-cache",
        "src/poseAdapter","src/graphAdapter","vendor_sources/EvoMemNav","models/graph001")
    for rel in readonly:
        p=ROOT/rel
        if not p.exists()or not p.resolve().is_relative_to(ROOT):raise RuntimeError("Missing private dependency "+rel)
        command+=["--ro-bind",str(p),str(p)]
    for name in ("tmp","cache"):
        (session/name).mkdir(exist_ok=True)
    command+=["--ro-bind",str(source_root),str(source_root),"--bind",str(output_root),str(output_root),
        "--bind",str(session),str(session),"--setenv","TMPDIR",str(session/"tmp"),
        "--setenv","HOME",str(session/"tmp"),
        "--setenv","HF_HOME",str(session/"cache/huggingface"),
        "--setenv","TORCH_HOME",str(session/"cache/torch"),
        "--setenv","TORCH_EXTENSIONS_DIR",str(session/"cache/torch_extensions"),
        "--setenv","TRITON_CACHE_DIR",str(session/"cache/triton"),
        "--setenv","NUMBA_CACHE_DIR",str(session/"cache/numba"),
        "--setenv","XDG_CACHE_HOME",str(session/"cache"),"--setenv","CUDA_CACHE_PATH",str(session/"cache/cuda"),
        "--setenv","MPLCONFIGDIR",str(session/"cache/matplotlib"),"--setenv","YOLO_CONFIG_DIR",str(session/"cache/yolo"),
        "--setenv","PYTHONDONTWRITEBYTECODE","1","--setenv","PYTHONNOUSERSITE","1",
        "--setenv","HF_HUB_OFFLINE","1","--setenv","TRANSFORMERS_OFFLINE","1",
        "--setenv","YOLO_AUTOINSTALL","false","--setenv","MPLBACKEND","Agg",
        "--setenv","NUMBA_NUM_THREADS","4","--setenv","OMP_NUM_THREADS","4","--setenv","MKL_NUM_THREADS","1",
        "--setenv","OPENBLAS_NUM_THREADS","1","--setenv","LD_LIBRARY_PATH",str(ROOT/"runtime/awarevln/lib"),
        "--chdir",str(ROOT),"--",str(ROOT/"runtime/graph_memory/perception/bin/python"),"-I","-B",
        str(ROOT/"src/graphAdapter/map_memory/worker.py"),"worker","--session",str(session),
        "--source-root",str(source_root),"--output-root",str(output_root)]
    return command

def _stop_owned(process):
    if process.poll()is not None:return process.returncode
    try:os.killpg(process.pid,signal.SIGTERM)
    except ProcessLookupError:return process.wait(timeout=10)
    try:return process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid,signal.SIGKILL);return process.wait(timeout=10)

def broker_connection(channel,environment):
    process=None;stream=None
    try:
        peer=struct.unpack("3i",channel.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        if peer[1]!=os.getuid():raise PermissionError("Memory broker peer UID mismatch")
        request=json.loads(channel.recv(16384))
        if set(request)!={"op","session","source_root","output_root"}or request["op"]!="spawn":
            raise ValueError("Fixed memory spawn envelope required")
        session=Path(request["session"])
        command=isolated_command(session,request["source_root"],request["output_root"])
        stream=(session/"worker.log").open("x")
        parent,child=socket.socketpair()
        try:
            process=subprocess.Popen(command,cwd=ROOT,env=environment,stdin=child,
                stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
            start=Path(f"/proc/{process.pid}/stat").read_text().split()[21]
            data=json.dumps(dict(status="spawned",pid=process.pid,starttime=start,command=command)).encode()
            channel.sendmsg([data],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,struct.pack("i",parent.fileno()))])
        finally:parent.close();child.close()
        while True:
            data=channel.recv(16384)
            if not data:break
            command=json.loads(data)
            if command=={"op":"poll"}:reply=dict(status="ok",returncode=process.poll())
            elif set(command)=={"op","timeout"}and command["op"]=="wait":
                timeout=command["timeout"]
                if not isinstance(timeout,(float,int))or not 0<=timeout<=180:raise ValueError("Wait timeout budget")
                try:reply=dict(status="ok",returncode=process.wait(timeout=timeout))
                except subprocess.TimeoutExpired:reply=dict(status="timeout")
            else:raise ValueError("Unsupported memory broker operation")
            channel.send(json.dumps(reply).encode())
    except BaseException as error:
        try:channel.send(json.dumps(dict(status="error",error=repr(error))).encode())
        except OSError:pass
    finally:
        if process is not None:_stop_owned(process)
        if stream is not None:stream.close()
        channel.close()

def broker_main(directory,parent_pid):
    directory=owned_path(directory,ROOT/"runtime/graph_memory/brokers",must_exist=True)
    if ctypes.CDLL(None).prctl(1,signal.SIGTERM)!=0:raise OSError("Cannot bind broker lifetime")
    if os.getppid()!=parent_pid:raise RuntimeError("Launcher exited before memory broker")
    environment={k:os.environ[k]for k in ("CUDA_VISIBLE_DEVICES","CUDA_DEVICE_ORDER","PATH","LANG","LC_ALL")if k in os.environ}
    environment.update(PYTHONDONTWRITEBYTECODE="1",PYTHONNOUSERSITE="1")
    listener=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET)
    listener.bind(str(directory/"broker.sock"));os.chmod(directory/"broker.sock",0o600);listener.listen(4)
    (directory/"ready.json").write_text(json.dumps(dict(pid=os.getpid(),starttime=Path("/proc/self/stat").read_text().split()[21])))
    slots=threading.BoundedSemaphore(4)
    while True:
        channel,_=listener.accept()
        if not slots.acquire(blocking=False):
            channel.send(json.dumps(dict(status="error",error="Memory worker capacity exhausted")).encode());channel.close();continue
        def run(client):
            try:broker_connection(client,environment)
            finally:slots.release()
        threading.Thread(target=run,args=(channel,),daemon=True).start()

def validate_mapping_profile(profile):
    import math
    from graphAdapter.map_memory.retrieval import retrieval_settings
    retrieval_settings(profile)
    if type(profile.get('separate_same_frame_claims',False)) is not bool:
        raise ValueError('separate_same_frame_claims must be boolean')
    if type(profile.get('async_admission',False))is not bool:raise ValueError('async_admission must be boolean')
    if type(profile.get("resources",{}).get("parallel_geometry_scene",False)) is not bool:
        raise ValueError("parallel_geometry_scene must be boolean")
    mode=profile.get("pose_input_mode","native_corrected")
    if mode not in ("native_corrected","continuous","provider_pose"):
        raise ValueError("Unknown pose input mode")
    source=profile.get('pose_provider','cuvslam_rtabmap_rgbd')
    if source not in ('cuvslam_rtabmap_rgbd','simulator_ground_truth'):raise ValueError('Unknown worker pose provider')
    if source=='simulator_ground_truth' or mode=='provider_pose':
        from graphAdapter.interfaces.pose.policy import require_simulator_mapping_profile
        require_simulator_mapping_profile(profile)
    if mode=="continuous":
        policy=profile.get("correction",{})
        for key in ("max_correction_difference_m","mapping_point_radius_m"):
            value=policy.get(key)
            if type(value) not in (int,float) or not math.isfinite(value):
                raise ValueError("Finite numeric mapping policy required: "+key)
        if policy["max_correction_difference_m"]<=0 or policy["mapping_point_radius_m"]<0:
            raise ValueError("Invalid mapping error bound or reference radius")
    background=profile.get('background_correction',{})
    if not isinstance(background,dict) or type(background.get('enabled',False)) is not bool:
        raise ValueError('background_correction requires an explicit boolean enabled field')
    if background.get('enabled'):
        if mode!='continuous' or profile.get('async_admission') is not True or profile.get('execution_mode','live')!='live':
            raise ValueError('Background correction requires continuous live async admission')
        for key in ('journal_bytes','journal_entries'):
            if type(background.get(key))is not int or background[key]<=0:raise ValueError('Positive background limit required: '+key)
        timeout=background.get('drain_timeout_s')
        if type(timeout)not in(int,float) or not math.isfinite(timeout) or timeout<=0:raise ValueError('Positive finite background drain timeout required')
    return mode


class MemoryWorkerClient:
    """Lightweight host endpoint;never imports Torch/detectors or appends model input."""
    def __init__(self,source_root,output_root,profile):
        mode=validate_mapping_profile(profile)
        expected_contract=None
        if mode=="continuous":
            from poseAdapter.interfaces.mapping import mapping_contract_identity,require_mapping_contract
            expected_contract=mapping_contract_identity()
        self.source_root=Path(source_root).absolute();self.output_root=Path(output_root).absolute()
        from .storage.routing import from_environment,create_process_scope,bind_process_scope
        self.routing=from_environment();self.routing_episode=None
        if self.routing is not None:create_process_scope(self.routing.root,self.output_root,'memory_output',defer_marker=True)
        else:self.output_root.mkdir(parents=True,exist_ok=False)
        suffix=Path(self.routing.run['run_uid'])/self.routing.worker if self.routing is not None else Path()
        self.profile=dict(profile,routed_storage=True)if self.routing is not None else profile
        self.session=ROOT/"runtime/graph_memory/sessions"/suffix/uuid.uuid4().hex
        if self.routing is not None:create_process_scope(self.routing.root,self.session,'memory_session')
        else:self.session.mkdir(parents=True,mode=0o700)
        broker=os.environ.get("GRAPH_MEMORY_BROKER")
        if not broker:raise RuntimeError("Use the dedicated protected memory broker")
        self.control=None;self.channel=None;descriptors=[]
        try:
            self.control=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET);self.control.settimeout(180)
            self.control.connect(broker)
            self.control.send(json.dumps(dict(op="spawn",session=str(self.session),source_root=str(self.source_root),output_root=str(self.output_root))).encode())
            data,ancillary,flags,_=self.control.recvmsg(65536,socket.CMSG_SPACE(struct.calcsize("i")))
            # Acquire/track every transferred FD before parsing a possibly bad
            # reply. Failed construction has no caller available to close them.
            malformed=False
            for level,kind,payload in ancillary:
                if level==socket.SOL_SOCKET and kind==socket.SCM_RIGHTS:
                    count=len(payload)//struct.calcsize("i")
                    descriptors+=list(struct.unpack("i"*count,payload[:count*struct.calcsize("i")]))
                    malformed|=len(payload)%struct.calcsize("i")!=0
            if malformed or flags&socket.MSG_CTRUNC:raise RuntimeError("Truncated memory IPC descriptor reply")
            identity=json.loads(data)
            if identity.get("status")!="spawned":raise RuntimeError("Memory worker spawn failed: "+str(identity))
            if len(descriptors)!=1:raise RuntimeError("One private memory IPC channel required")
            self.channel=socket.socket(fileno=descriptors[0]);descriptors.clear()
            self.channel.settimeout(profile.get("frame_timeout_seconds",300))
            self.identity=identity;self.active_episode=None;self.count=0;self.lifecycle_session=None
            if self.routing is not None:
                process_owner=dict(pid=identity['pid'],starttime=identity['starttime'])
                bind_process_scope(self.routing.root,self.session,process_owner)
                bind_process_scope(self.routing.root,self.output_root,process_owner)
            (self.session/"process.json").write_text(json.dumps(identity,indent=2))
            if expected_contract is not None:
                # Old consumers reject this lightweight operation before any
                # initialize/model request can be sent to an incompatible worker.
                self.capabilities=self.call(dict(op="capabilities",verify_background_runtime=bool(self.profile.get('background_correction',{}).get('enabled'))))
                require_mapping_contract(expected_contract,self.capabilities.get("mapping_contract"))
                if self.profile.get('background_correction',{}).get('enabled') and 'background_correction' not in self.capabilities.get('features',[]):
                    raise RuntimeError('Private worker does not support background correction publication protocol')
                if self.profile.get('background_correction',{}).get('enabled') and (self.capabilities.get('background_runtime')or{}).get('kind')!='memory_worker_bwrap':
                    raise RuntimeError('Private worker background child runtime was not verified')
            if mode=='provider_pose':
                self.capabilities=self.call(dict(op='capabilities'))
                if 'provider_pose' not in self.capabilities.get('features',[]):raise RuntimeError('Worker lacks explicit pose-provider protocol')
            from graphAdapter.map_memory.retrieval import retrieval_settings
            if retrieval_settings(self.profile)is not None and 'snapshot_retrieval_v1'not in self.capabilities.get('features',[]):
                raise RuntimeError('Private worker lacks the snapshot retrieval contract')
            self.initialization_receipt=self.call(dict(op="initialize",profile=self.profile,
                expected_mapping_contract=expected_contract))
            if expected_contract is not None:
                require_mapping_contract(expected_contract,self.initialization_receipt.get("mapping_contract"))
        except BaseException:
            for descriptor in descriptors:
                try:os.close(descriptor)
                except OSError:pass
            for channel in (self.channel,self.control):
                if channel is not None:
                    try:channel.close()
                    except OSError:pass
            raise

    def call(self,message):
        try:
            send(self.channel,message);reply=receive(self.channel)
            if not isinstance(reply,dict)or reply.get('status')not in ('ok','error'):
                raise ValueError('Invalid private memory RPC reply envelope')
        except (OSError,EOFError,ValueError)as error:
            self.channel.close()
            raise MemoryTransportError('Private memory RPC framing/transport failed: '+str(error))from error
        if reply.get("status")!="ok":
            error=RuntimeError("Memory worker "+reply.get("error","unknown error"))
            error.prior_publications=reply.get('prior_publications',[])
            error.remote_error_type=reply.get('error_type','unknown')
            raise error
        return reply

    def read_memory(self,request):
        from graphAdapter.map_memory.retrieval import FrozenMemoryRead,retrieval_settings
        item=FrozenMemoryRead.create(request);value=item.request;settings=retrieval_settings(self.profile)
        if settings is None or value['mode']!=settings['mode']:
            raise ValueError('Read mode is not explicitly enabled in this worker profile')
        if value['query']['episode_uid']!=self.active_episode:raise ValueError('Read belongs to another active memory episode')
        return item.validate_reply(self.call(dict(op='read_memory',request=value))['result'])

    def _begin_episode(self,packet):
        if self.active_episode==packet.episode_uid:return
        return self.begin_episode(packet.episode_uid,packet.to_record()['identity'])

    def begin_episode(self,episode_uid,identity):
        if self.active_episode==episode_uid:return
        if self.active_episode is not None:raise RuntimeError('End previous memory episode before reset')
        binding=self.profile.get('lifecycle_binding')
        owner=None
        from .storage.lifecycle import EpisodeLifecycle,EpisodeSession,canonical
        import hashlib
        opaque=hashlib.sha256(canonical(identity['member'])).hexdigest()
        expected=self.output_root/'episodes'/identity['dataset']/opaque/'attempt_000'
        routing=getattr(self,'routing',None)
        if routing is not None:
            owner=routing.episode(identity);self.routing_episode=owner
            routing.register(owner,'memory',expected.parent,'memory-owner')
            self.lifecycle_session=routing.session(owner,'memory')
        elif binding:
            registered=json.loads((Path(binding['root'])/'retention_plan.json').read_bytes())
            entry=next((x for x in registered['entries']if x['member']==identity['member']),None)
            if entry is None:raise RuntimeError('Memory member absent from retention plan')
            owner=EpisodeLifecycle(binding['root'],entry['key'],'shadow',binding['attempt'],plan_sha256=binding['plan_sha256'])
            if not owner.work.exists():owner.create_work()
            owner._owned();self.lifecycle_session=EpisodeSession(owner,'memory')
        if owner is not None:self.lifecycle_session.bind_remote_memory(expected,episode_uid)
        self.call(dict(op='begin_episode',episode_uid=episode_uid,identity=identity))
        self.active_episode=episode_uid
        self.active_read_root=expected.resolve()

    def record_source(self,packet,receipt):
        if self.profile.get('execution_mode')!='archive_only':raise RuntimeError('Source archiver requires explicit archive-only mode')
        from graphAdapter.observation_packet import thaw
        self._begin_episode(packet)
        return self.call(dict(op='archive_source',packet=packet.to_record(),receipt=thaw(receipt)))['result']

    def consume(self,packet,receipt,*,pose_adapter=None,force_mapping_correction=False,frozen_mapping_sample=_FROZEN_UNSET):
        from graphAdapter.observation_packet import thaw
        if getattr(self,'profile',{}).get('execution_mode','live')!='live':raise RuntimeError('Live consume cannot use archive-only worker')
        continuous=getattr(self,"profile",{}).get("pose_input_mode","native_corrected")=="continuous"
        provided=getattr(self,'profile',{}).get('pose_input_mode')=='provider_pose'
        if packet.pose_provider!=getattr(self,'profile',{}).get('pose_provider','cuvslam_rtabmap_rgbd'):
            raise ValueError('Packet pose provider differs from worker profile')
        if provided and (pose_adapter is not None or force_mapping_correction or frozen_mapping_sample is not _FROZEN_UNSET):
            raise ValueError('Provider pose consumes frozen packet only, without native adapter/correction input')
        frozen=frozen_mapping_sample is not _FROZEN_UNSET
        if frozen:
            if not continuous or pose_adapter is not None:raise ValueError("Frozen input requires continuous mode without a live adapter")
            from poseAdapter.interfaces.mapping import MappingSample
            if frozen_mapping_sample is not None:
                if not isinstance(frozen_mapping_sample,MappingSample):raise TypeError("Validated frozen MappingSample required")
                if (frozen_mapping_sample.episode_id,frozen_mapping_sample.frame_id,frozen_mapping_sample.timestamp_ns)!=(packet.episode_uid,packet.frame_uid,packet.sensor_timestamp_ns):
                    raise ValueError("Frozen mapping source differs from observation")
            elif packet.pose_record.get("geometry_status")=="available":
                raise ValueError("Measured observation requires its frozen mapping sample")
        if continuous and not frozen and (pose_adapter is None or not hasattr(pose_adapter,"get_mapping_frame_snapshot")):
            raise RuntimeError("Continuous mapping requires the versioned PoseAdapter mapping interface")
        self._begin_episode(packet)
        self._last_mapping_input=(packet,receipt,pose_adapter)
        bindings=packet.to_record()["pose_record"].get("spatial_bindings")
        for attempt in range(1 if frozen or provided else 8):
            mapping_sample=frozen_mapping_sample if frozen else None
            if continuous and not frozen:
                mapping_sample=pose_adapter.get_mapping_frame_snapshot(packet.frame_uid,
                    timestamp_ns=packet.sensor_timestamp_ns,episode_id=packet.episode_uid)
            if continuous:
                if mapping_sample is not None:bindings=mapping_sample.bindings
            elif pose_adapter is not None:
                estimate,current=pose_adapter.get_frame_snapshot(packet.frame_uid,timestamp_ns=packet.sensor_timestamp_ns,episode_id=packet.episode_uid)
                if current is not None:bindings=current
            request=dict(op="prepare",packet=packet.to_record(),receipt=thaw(receipt),bindings=bindings)
            if continuous:
                request.update(mapping_sample=mapping_sample.to_record() if mapping_sample is not None else None,
                    force_mapping_correction=force_mapping_correction or (bool(packet.action.get("terminal")) and not self.profile.get("background_correction",{}).get("enabled",False)))
            reply=self.call(request)
            if reply["result"]["duplicate"]:return reply["result"]
            target=reply["result"]["target_pose_map_version"]
            check_target = not frozen and (not continuous or reply["result"].get("mapping_correction_applied",False))
            if pose_adapter is not None and check_target:
                estimate,current=pose_adapter.get_frame_snapshot(packet.frame_uid,timestamp_ns=packet.sensor_timestamp_ns,episode_id=packet.episode_uid)
                latest=current["map_version"]if current is not None else target
                if latest!=target:
                    self.call(dict(op="cancel",frame_uid=packet.frame_uid,reason="pose_revision_advanced",latest=latest))
                    bindings=current;continue
            result=self.call(dict(op="commit",frame_uid=packet.frame_uid,target_pose_map_version=target,
                                 candidate_hash=reply["result"]["candidate_hash"]))["result"]
            validate_prepared_commit(result,target,packet)
            if continuous or provided:result.update(frame_uid=packet.frame_uid,source_packet_event_seq=packet.event_seq)
            self.count+=1;return result
        raise RuntimeError("Memory pose target did not stabilize;no mixed revision published")

    def flush_mapping_correction(self,*,frozen_correction=_FROZEN_UNSET,packet=None):
        frozen=frozen_correction is not _FROZEN_UNSET
        last=getattr(self,"_last_mapping_input",None)
        if packet is None:
            if last is None:raise RuntimeError("Correction requires its source packet")
            packet=last[0]
        adapter=None if frozen else (last[2] if last is not None else None)
        if frozen:
            from poseAdapter.interfaces.mapping import CorrectionSnapshot
            if frozen_correction is not None and not isinstance(frozen_correction,CorrectionSnapshot):
                raise TypeError("Validated frozen CorrectionSnapshot required")
            if frozen_correction is not None:
                if (frozen_correction.episode_id,frozen_correction.frame_id)!=(packet.episode_uid,packet.frame_uid):
                    raise ValueError("Frozen correction source frame/episode mismatch")
                if (frozen_correction.timestamp_ns>packet.sensor_timestamp_ns or
                        (packet.pose_record.get("geometry_status")=="available" and frozen_correction.timestamp_ns!=packet.sensor_timestamp_ns)):
                    raise ValueError("Frozen correction timestamp differs from source observation")
        elif adapter is None or not hasattr(adapter,"get_mapping_correction_snapshot"):
            raise RuntimeError("Final mapping flush requires the correction snapshot interface")
        for _ in range(1 if frozen else 8):
            target=frozen_correction if frozen else adapter.get_mapping_correction_snapshot()
            if target is None:
                return dict(duplicate=True,reason="no_published_correction")
            ready=self.call(dict(op="prepare_correction",correction=target.to_record()))["result"]
            if ready["duplicate"]:return ready
            latest=target if frozen else adapter.get_mapping_correction_snapshot()
            if latest is None or latest.binding_digest!=target.binding_digest:
                self.call(dict(op="cancel",frame_uid=ready["frame_uid"],reason="correction_target_advanced"))
                continue
            result=self.call(dict(op="commit",frame_uid=ready["frame_uid"],
                target_pose_map_version=ready["target_pose_map_version"],candidate_hash=ready["candidate_hash"]))["result"]
            validate_prepared_commit(result,ready["target_pose_map_version"],packet)
            result.update(frame_uid=packet.frame_uid,source_packet_event_seq=packet.event_seq)
            self.count+=1
            return result
        raise RuntimeError("Final correction target did not stabilize")

    def end_episode(self,cancelled_actions,*,frozen_correction=_FROZEN_UNSET):
        if self.active_episode is not None:
            final_publication=None
            if getattr(self,"profile",{}).get("pose_input_mode","native_corrected")=="continuous":
                if frozen_correction is _FROZEN_UNSET:
                    final_publication=self.flush_mapping_correction()
                elif frozen_correction is not None:
                    final_publication=self.flush_mapping_correction(frozen_correction=frozen_correction)
            request=dict(op="end_episode",cancelled_actions=list(cancelled_actions))
            owner=getattr(self,'lifecycle_session',None)
            if owner is not None:request['release_ticket']=owner.ticket
            result=self.call(request)
            if owner is not None:
                owner.accept_remote_acknowledgement(result['lifecycle']['session_acknowledgement'])
                self.lifecycle_session=None
                if getattr(self,'routing',None)is not None:self.routing.accept(self.routing_episode,'memory',result['lifecycle']['session_acknowledgement'])
            self.active_episode=None
            self._last_mapping_input=None
            if final_publication is not None:result["final_publication"]=final_publication
            return result

    def close(self,abort_reason=None):
        try:
            if self.active_episode is not None and abort_reason is not None:
                request=dict(op="abort_episode",reason=str(abort_reason))
                owner=getattr(self,'lifecycle_session',None)
                if owner is not None:request['release_ticket']=owner.ticket
                aborted=self.call(request)
                if owner is not None:
                    owner.accept_remote_acknowledgement(aborted['lifecycle']['session_acknowledgement'])
                    self.lifecycle_session=None
                    if getattr(self,'routing',None)is not None:self.routing.accept(self.routing_episode,'memory',aborted['lifecycle']['session_acknowledgement'])
                (self.session/"abort-lifecycle.json").write_text(json.dumps(aborted,indent=2))
                self.active_episode=None
            if self.active_episode is not None:self.end_episode([])
            self.call(dict(op="shutdown"))
            self.control.send(json.dumps(dict(op="wait",timeout=120)).encode())
            outcome=json.loads(self.control.recv(65536))
            if outcome.get("returncode")!=0:raise RuntimeError("Memory worker did not close cleanly: "+str(outcome))
            (self.session/"cleanup.json").write_text(json.dumps(dict(graceful=True,returncode=0)))
        finally:
            self.channel.close();self.control.close()


def release_memory_episode(store, *, owner_session=None, remote_ticket=None):
    """Actual worker terminal release, shared by RPC end and CPU qualification."""
    if owner_session is not None and remote_ticket is not None:raise RuntimeError('One memory owner credential required')
    if remote_ticket is not None:
        from .storage.lifecycle import close_remote_memory_session
        acknowledgement=close_remote_memory_session(remote_ticket,store)
        release=acknowledgement['payload']['observed']['release']
    elif owner_session is None:
        store.close()
        release=store.release_audit()
        acknowledgement=None
    else:
        acknowledgement=owner_session.close_memory(store)
        release=acknowledgement["payload"]["observed"]["release"]
    if not release["memory_closed"] or not release["pins_zero"] or any(release["cache_entries"].values()):
        raise RuntimeError("Memory episode failed actual release audit")
    return dict(release=release,session_acknowledgement=acknowledgement)

def worker_main(session,source_root,output_root):
    sys.path.insert(0,str(ROOT/"runtime/graph_memory/package_root"))
    sys.path.insert(0,str(ROOT/"vendor_sources/EvoMemNav"))
    # Both public adapters come from the same declared, read-only source release.
    # The shared package_root contains a legacy pose alias and must not win.
    sys.path.insert(0,str(ROOT/"src"))
    import poseAdapter
    from poseAdapter.interfaces.mapping import mapping_contract_identity,require_mapping_contract
    if Path(poseAdapter.__file__).resolve().parent!=(ROOT/"src/poseAdapter").resolve():
        raise RuntimeError("Private worker loaded an undeclared PoseAdapter package")
    mapping_contract=mapping_contract_identity()
    import hashlib,resource,random
    import numpy as np,torch
    from omegaconf import OmegaConf
    from .service import MapMemoryService, uses_filesystem_capacity
    from .perception.scene import RealPerceptionModels
    from .storage.store import EpisodeStore,canonical,load_episode
    from .visualization import render_episode
    session=Path(session);source_root=Path(source_root);output_root=Path(output_root)
    channel=socket.socket(fileno=0)
    profile=None;models=None;service=None;store=None;prepared=None;archive_views={}
    background=None;correction_request=None;background_runtime=None
    retrieval_worker=None;read_options=None
    boundary=dict(annotations_absent=not(ROOT/"data").exists(),
        main_weights_absent=not(ROOT/"models/awarevln").exists(),
        evaluator_private_absent=not(output_root.parent/"evaluation_private").exists(),
        host_episode_traces_absent=not(source_root.parent/'episodes').exists(),
        host_native_results_absent=not(source_root.parent/'native').exists(),
        other_pose_sessions_absent=not(ROOT/'runtime/pose/sessions').exists())
    import importlib.util
    boundary['simulator_provider_absent']=importlib.util.find_spec('SimulatorAdapter') is None
    if not all(boundary.values()):raise RuntimeError("Memory input boundary failed")
    # This process is protected by the broker's bwrap namespace, not the host's
    # later Landlock marker. Children inherit these exact private mounts.
    os.environ['GRAPH_MEMORY_PRIVATE_RUNTIME']=json.dumps(dict(kind='memory_worker_bwrap',
        owner_pid=os.getpid(),mount_namespace=os.readlink('/proc/self/ns/mnt')))
    (session/"input-boundary.json").write_text(json.dumps(boundary,indent=2))
    def load_ref(ref,packet):
        if ref is None:return None
        path=Path(ref).resolve();expected=source_root/packet["episode_uid"]/("f"+format(packet["capture_seq"],"06d"))
        if path.parent!=expected:raise ValueError("Input belongs to another source endpoint")
        return np.load(path,allow_pickle=False)
    def resource_state():
        page_size=os.sysconf("SC_PAGE_SIZE")
        current_rss=int(Path("/proc/self/statm").read_text().split()[1])*page_size
        try:
            fields={line.split(":")[0]:int(line.split()[1])*1024
                for line in Path("/proc/self/smaps_rollup").read_text().splitlines()if line.startswith("Private_")}
            uss=sum(fields.values())
        except OSError:uss=None
        try:
            io={line.split(":")[0]:int(line.split(":")[1])for line in Path("/proc/self/io").read_text().splitlines()}
        except OSError:io=None
        return dict(process_io_lifetime=io,scope="private_worker_current;allocator_and_IO_scope_are_explicit",
            rss_current_bytes=current_rss,uss_bytes=uss,
            rss_peak_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
            rss_peak_scope="process_lifetime",open_fd_count=len(list(Path("/proc/self/fd").iterdir())),
            cuda_allocated_bytes=torch.cuda.memory_allocated()if torch.cuda.is_available()else 0,
            cuda_reserved_bytes=torch.cuda.memory_reserved()if torch.cuda.is_available()else 0,
            cuda_allocated_peak_bytes=torch.cuda.max_memory_allocated()if torch.cuda.is_available()else 0,
            cuda_reserved_peak_bytes=torch.cuda.max_memory_reserved()if torch.cuda.is_available()else 0)

    completed_bytes=0
    def prepare_endpoint(request):
        nonlocal correction_request
        correction_request=None
        if background is not None:background.advance()
        p=request["packet"]
        from graphAdapter.observation_packet import ObservationPacket
        checked=ObservationPacket(**p)
        if checked.pose_provider!=profile.get('pose_provider','cuvslam_rtabmap_rgbd'):raise ValueError('Worker rejected another pose provider')
        if profile.get('pose_input_mode')=='provider_pose' and (request.get('mapping_sample') is not None or request.get('force_mapping_correction')):
            raise ValueError('Simulator pose cannot carry native correction inputs')
        resources=profile.get("resources",{})
        if not uses_filesystem_capacity(resources) and p["capture_seq"]%16==1:
            run_bytes=sum(f.stat().st_size for f in output_root.rglob("*")if f.is_file())if profile.get("routed_storage")else completed_bytes+store.accounted_bytes()
            if run_bytes>resources.get("max_worker_artifact_bytes",resources.get("max_run_bytes",2**63)):
                raise RuntimeError("Worker memory artifact budget exceeded;source/history preserved")
        rgb=load_ref(p["raw_rgb_ref"],p);raw=load_ref(p["raw_depth_ref"],p)
        depth=load_ref(p["aligned_ref"],p);mask=None
        if depth is not None:mask=np.load(Path(p["aligned_ref"]).parent/"depth_valid_mask.npy",allow_pickle=False)
        transform=profile.get("host_transform")
        if transform is None or transform.get("kind")!="identity":
            raise RuntimeError("Explicit verified host transform is required")
        started=time.perf_counter()
        mapping_options={}
        if profile.get("pose_input_mode","native_corrected")=="continuous":
            from poseAdapter.interfaces.mapping import MappingSample
            encoded=request.get("mapping_sample")
            sample=MappingSample.from_record(encoded) if encoded is not None else None
            apply=False
            if sample is not None:
                policy=profile["correction"]
                assessment=service.assess_mapping_correction(sample,
                    max_difference_m=policy["max_correction_difference_m"],point_radius_m=policy["mapping_point_radius_m"],
                    T_base_camera=p["T_base_camera"],
                    current_source_radius_m=service.source_radius(depth,mask,p["K"]))
                apply=bool(request.get("force_mapping_correction")) or assessment["action"]=="correct"
            if background is not None:
                if apply and sample is not None:
                    from poseAdapter.interfaces.mapping import CorrectionSnapshot
                    correction_request=CorrectionSnapshot(sample.episode_id,sample.episode_instance,sample.frame_id,
                        sample.timestamp_ns,sample.native_map_version,sample.bindings_json,sample.odometry_epoch)
                apply=False
            mapping_options=dict(mapping_sample=sample,apply_mapping_correction=apply)
        result=service.prepare_endpoint(p,rgb,raw,depth,mask,bindings=request["bindings"],
            host_view=rgb,host_transform=transform,committed_receipt=request["receipt"],**mapping_options)
        result["mapping_correction_applied"]=mapping_options.get("apply_mapping_correction",False)
        store._append("execution.jsonl",dict(kind="memory_prepare",frame_uid=p["frame_uid"],
            seconds=time.perf_counter()-started,rebuild=result.get("rebuild",False),
            correction_strategy=result.get("correction_strategy"),replayed_frames=result.get("replayed_frames"),
            replay_storage=result.get("replay_storage"),processing_metrics=result.get("processing_metrics")))
        return result

    def finish_episode(request):
        if profile.get('execution_mode')=='archive_only':
            reader=store.open_reader()
            try:inspection=reader.verify(hashes=True,references=True)
            finally:reader.close()
            summary=dict(episode_uid=store.episode_uid,frames=len(archive_views),inspection=inspection,
                execution_mode='archive_only',models_loaded=False,geometry_processed=False)
            (store.root/'episode_summary.json').write_text(json.dumps(summary,indent=2))
            return summary
        reader=store.open_reader()
        try:inspection=reader.verify()
        finally:reader.close()
        views=service.graph["views"]
        eligible=[]
        for view in views.values():
            meta=service.frames[view["frame_uid"]]
            if (view["capture_seq"]>1 and meta["files"]["rgb"]is not None
                and "aligned_depth"in meta["arrays"]and meta["K"]is not None
                and meta["T_base_camera"]is not None):eligible.append(view)
        semantic={uid for entity in service.graph["entities"]if entity["epoch"]==service.epoch for uid in entity.get("view_uids",[])}
        summary=dict(episode_uid=store.episode_uid,frames=len(views),eligible_endpoints=len(eligible),
            geometry_fused=sum(v["geometry_fused"]for v in eligible),perception_complete=sum(v["perception_complete"]for v in views.values()),
            semantic_contribution_frames=sum(v["frame_uid"]in semantic for v in eligible),
            tiles=len(service.geometry.records),objects=len(service.scene.objects),anchors=len(service.scene.anchor_views),
            snapshot_id=service.pointer["snapshot_id"],pose_map_version=service.version,inspection=inspection,
            cancelled_actions=request["cancelled_actions"],rss_peak_kb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            resource_samples=service.resource_samples,
            disk_bytes=sum(p.stat().st_size for p in store.root.rglob("*")if p.is_file()))
        if profile.get("render_on_episode_end",True):
            summary["render"]=render_episode(store.root,out=store.root/"visualizations",height_slice="auto")
            store.register_rendered_outputs()
        (store.root/"episode_summary.json").write_text(json.dumps(summary,indent=2))
        return summary

    try:
        while True:
            try:request=receive(channel)
            except EOFError:break
            try:
                op=request["op"]
                if op=="capabilities":
                    if request.get('verify_background_runtime'):
                        from .correction_runtime import probe_child_runtime
                        background_runtime=probe_child_runtime()
                    send(channel,dict(status="ok",mapping_contract=mapping_contract,background_runtime=background_runtime,
                        pose_package_file=str(Path(poseAdapter.__file__).resolve()),
                        features=["continuous_mapping","independent_correction","parallel_geometry_scene","background_correction","provider_pose","snapshot_retrieval_v1"]))
                elif op=="initialize":
                    if profile is not None:raise ValueError("Worker already initialized")
                    incoming=request["profile"];mode=validate_mapping_profile(incoming)
                    if incoming.get('background_correction',{}).get('enabled') and background_runtime is None:
                        from .correction_runtime import probe_child_runtime
                        background_runtime=probe_child_runtime()
                    if mode=="continuous":
                        require_mapping_contract(mapping_contract,request.get("expected_mapping_contract"))
                    # Contract rejection occurs before weight reads or model/GPU construction.
                    (session/"initialization-contract.json").write_text(json.dumps(dict(mode=mode,contract=mapping_contract,checked=mode=="continuous"),indent=2))
                    from graphAdapter.map_memory.retrieval import retrieval_settings
                    read_options=retrieval_settings(incoming)
                    profile=incoming;torch.manual_seed(77);np.random.seed(77);random.seed(77);torch.set_num_threads(4)
                    execution_mode=profile.get('execution_mode','live')
                    if execution_mode not in('live','archive_only'):raise ValueError('Unknown memory execution mode')
                    if execution_mode=='archive_only':
                        model_identity=dict(mode='archive_only',models_loaded=False,navigation_eligible=False)
                        send(channel,dict(status='ok',model_identity=model_identity,input_boundary=boundary,resources=resource_state(),
                            mapping_contract=mapping_contract,pose_package_file=str(Path(poseAdapter.__file__).resolve())))
                    else:
                        (session/"model-initialization-started.json").write_text(json.dumps(dict(after_contract=True)))
                        cfg=OmegaConf.load(ROOT/"vendor_sources/EvoMemNav/cfg/evomemnav_goatbench.yaml")
                        cfg.data.object_classes_path=str(ROOT/"vendor_sources/EvoMemNav/data/scannet200_classes.txt")
                        cg=OmegaConf.load(ROOT/"vendor_sources/EvoMemNav/cfg/concept_graph.yaml")
                        cg.separate_same_frame_claims=profile.get("separate_same_frame_claims",False)
                        lock=json.loads((ROOT/"models/graph001/model_lock.json").read_bytes())
                        for name,expected in lock["weights"].items():
                            h=hashlib.sha256()
                            with(ROOT/"models/graph001"/name).open("rb")as asset:
                                for b in iter(lambda:asset.read(8*1024*1024),b""):h.update(b)
                            if h.hexdigest()!=expected:raise RuntimeError("Perception asset hash mismatch: "+name)
                        models=RealPerceptionModels(ROOT)
                        model_identity=dict(weights=lock["weights"],preprocess_hash=models.preprocess_hash,vocabulary_sha256=lock["vocabulary_sha256"])
                        send(channel,dict(status="ok",model_identity=model_identity,input_boundary=boundary,resources=resource_state(),
                            mapping_contract=mapping_contract,pose_package_file=str(Path(poseAdapter.__file__).resolve())))
                elif op=="begin_episode":
                    if profile is None:raise ValueError('Initialize worker before episode creation')
                    if store is not None:raise ValueError("Episode already active")
                    prepared=None;archive_views={}
                    episode=request["episode_uid"];identity=request["identity"]
                    dataset=identity["dataset"]
                    opaque=hashlib.sha256(canonical(identity["member"])).hexdigest()
                    path=output_root/"episodes"/dataset/opaque/"attempt_000"
                    store=EpisodeStore(path,episode,dataset=dataset)
                    if profile.get('execution_mode','live')=='live':
                        service=MapMemoryService(store,cfg,cg,models=models,model_identity=model_identity,
                            geometry_options=profile.get("geometry",{}),resource_limits=profile.get("resources",{}),
                            correction_options=profile.get("correction",{}))
                    if profile.get('background_correction',{}).get('enabled'):
                        from .correction_scheduler import WorkerCorrectionController
                        background=WorkerCorrectionController(service,output_root/'correction_work'/dataset/opaque/'attempt_000',dict(profile['background_correction'],
                            max_correction_difference_m=profile['correction']['max_correction_difference_m'],
                            mapping_point_radius_m=profile['correction']['mapping_point_radius_m']))
                    (path/"episode_scope.json").write_text(json.dumps(identity,indent=2))
                    send(channel,dict(status="ok",episode=str(path)))
                elif op=='archive_source':
                    if profile.get('execution_mode')!='archive_only'or store is None:raise ValueError('Source archive session required')
                    from graphAdapter.observation_packet import ObservationPacket
                    packet=ObservationPacket(**request['packet'])
                    if packet.pose_provider!=profile.get('pose_provider','cuvslam_rtabmap_rgbd'):raise ValueError('Archive pose provider differs from profile')
                    p=packet.to_record();receipt=request['receipt']
                    if not receipt.get('committed')or receipt.get('packet_record_hash')!=hashlib.sha256(canonical(p)).hexdigest():
                        raise ValueError('Committed source receipt mismatch')
                    rgb=load_ref(p['raw_rgb_ref'],p);raw=load_ref(p['raw_depth_ref'],p);depth=load_ref(p['aligned_ref'],p)
                    mask=None if depth is None else np.load(Path(p['aligned_ref']).parent/'depth_valid_mask.npy',allow_pickle=False)
                    store.archive_frame(p,rgb,raw,depth,mask,host_view=rgb,host_transform={'kind':'identity'})
                    archive_views[p['frame_uid']]=dict(frame_uid=p['frame_uid'],capture_seq=p['capture_seq'],
                        position_G=None,pose_map_version=None,geometry_fused=False,perception_complete=False,
                        execution_mode='archive_only')
                    version=p['pose_record'].get('map_version')or 0
                    pointer=store.publish(dict(episode_uid=p['episode_uid'],views=archive_views,entities=[],aliases=[],edges=[],tiles={},contributions=[]),
                        dict(pose_map_version=version),dict(capture_seq=p['capture_seq'],event_seq=p['event_seq']))
                    send(channel,dict(status='ok',result=dict(snapshot_id=pointer['snapshot_id'],versions=pointer['versions'],
                        cutoff=pointer['cutoff'],execution_mode='archive_only',geometry_processed=False,models_loaded=False)))
                elif op=='read_memory':
                    if retrieval_worker is None:
                        from .retrieval import WorkerRetrieval
                        retrieval_worker=WorkerRetrieval(ROOT)
                    result=retrieval_worker.read(request['request'],options=read_options,service=service,
                        store=store,models=models,model_identity=model_identity,prepared=prepared)
                    send(channel,dict(status='ok',result=result))
                elif op=="prepare":
                    if service is None:raise ValueError("No active memory episode")
                    prepared=prepare_endpoint(request)
                    send(channel,dict(status="ok",result=prepared))
                elif op=="prepare_correction":
                    if service is None:raise ValueError("No active memory episode")
                    if profile.get("pose_input_mode")=="provider_pose":raise ValueError("Simulator poses do not use native correction RPC")
                    from poseAdapter.interfaces.mapping import CorrectionSnapshot
                    target=CorrectionSnapshot.from_record(request["correction"])
                    if background is not None:
                        result=background.finish(target)
                        send(channel,dict(status="ok",result=result));background.acknowledge_sent()
                        prepared=None;continue
                    prepared=service.prepare_correction(target)
                    if prepared.get("duplicate") and service.pointer is not None:
                        # A no-op reports the real committed frontier, not a
                        # snapshot/cutoff invented from the correction request.
                        latest=max(service.frames.values(),key=lambda item:item["capture_seq"])
                        prepared=dict(prepared,snapshot_id=service.pointer["snapshot_id"],
                            versions=service.pointer["versions"],cutoff=service.pointer["cutoff"],
                            frame_uid=latest["frame_uid"],source_packet_event_seq=latest["event_seq"])
                    send(channel,dict(status="ok",result=prepared))
                elif op=="cancel":
                    if service.prepared is not None:
                        store._append("updates.jsonl",dict(kind="rebuild_interrupted",frame_uid=request["frame_uid"],reason=request["reason"],latest=request["latest"]))
                    service.prepared=None;prepared=None;send(channel,dict(status="ok"))
                elif op=="commit":
                    if prepared is None or prepared.get("candidate_hash")!=request["candidate_hash"]:raise ValueError("Candidate grant hash mismatch")
                    started=time.perf_counter()
                    result=service.publish_prepared(frame_uid=request["frame_uid"],target_pose_map_version=request["target_pose_map_version"])
                    if background is not None:background.after_observation_commit(correction_request)
                    store._append("execution.jsonl",dict(kind="memory_commit",frame_uid=request["frame_uid"],
                        seconds=time.perf_counter()-started,snapshot_id=result["snapshot_id"]))
                    reply=dict(snapshot_id=result["snapshot_id"],versions=result["versions"],cutoff=result["cutoff"])
                    if background is not None:reply['prior_publications']=background.receipts()
                    send(channel,dict(status="ok",result=reply))
                    if background is not None:background.acknowledge_sent()
                    prepared=None;correction_request=None
                elif op=="end_episode":
                    if retrieval_worker is not None:retrieval_worker.end_episode()
                    if background is not None:
                        background.assert_drained();background.close();background=None
                    summary=finish_episode(request)
                    episode_path=store.root
                    closure=release_memory_episode(store,remote_ticket=request.get('release_ticket'))
                    release=closure['release']
                    (episode_path/'episode_release.json').write_text(json.dumps(release,indent=2))
                    store=None;service=None;prepared=None;archive_views={}
                    completed_bytes+=sum(f.stat().st_size for f in episode_path.rglob("*")if f.is_file())
                    import gc
                    gc.collect()
                    send(channel,dict(status="ok",summary=summary,
                        lifecycle=dict(episode_released=store is None and service is None and prepared is None,
                            release_audit=release,session_acknowledgement=closure["session_acknowledgement"],fixed_models_loaded=models is not None,resources=resource_state())))
                elif op=="abort_episode":
                    if retrieval_worker is not None:retrieval_worker.end_episode()
                    if background is not None:
                        if service is not None:service.prepared=None
                        background.close();background=None
                    abort_closure=None
                    if store is not None:
                        store._append("errors.jsonl",dict(kind="attempt_aborted",reason=request["reason"]))
                        marker=store.root/"FAILED.json"
                        if not marker.exists():marker.write_text(json.dumps(dict(reason=request["reason"],committed_snapshot=service.pointer if service is not None else store.current)))
                        episode_path=store.root
                        abort_closure=release_memory_episode(store,remote_ticket=request.get('release_ticket'))
                        (episode_path/'episode_release.json').write_text(json.dumps(abort_closure['release'],indent=2))
                        store=None;service=None;prepared=None;archive_views={}
                        completed_bytes+=sum(f.stat().st_size for f in episode_path.rglob("*")if f.is_file())
                        import gc
                        gc.collect()
                    send(channel,dict(status="ok",
                        lifecycle=dict(episode_released=store is None and service is None and prepared is None,
                            session_acknowledgement=abort_closure['session_acknowledgement']if abort_closure else None,
                            release_audit=abort_closure['release']if abort_closure else None,
                            fixed_models_loaded=models is not None,resources=resource_state())))
                elif op=="shutdown":
                    if store is not None:raise RuntimeError("Active episode cannot be silently dropped")
                    send(channel,dict(status="ok"));break
                else:raise ValueError("Unsupported memory operation")
            except BaseException as error:
                if store is not None:
                    try:store._append("errors.jsonl",dict(op=request.get("op"),error=type(error).__name__+": "+str(error)))
                    except OSError:pass
                send(channel,dict(status="error",error_type=type(error).__name__,error=type(error).__name__+": "+str(error),
                    prior_publications=background.receipts() if background is not None else []))
    finally:
        if retrieval_worker is not None:retrieval_worker.close()
        if background is not None:
            if service is not None:service.prepared=None
            background.close()
        if store is not None:store.close()
        channel.close()

def main():
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest="mode",required=True)
    broker=sub.add_parser("broker");broker.add_argument("--directory",required=True);broker.add_argument("--parent-pid",type=int,required=True)
    worker=sub.add_parser("worker")
    for name in ("session","source-root","output-root"):worker.add_argument("--"+name,required=True)
    args=parser.parse_args()
    if args.mode=="broker":broker_main(args.directory,args.parent_pid)
    else:
        # File execution under-I has no package context;only private declared roots are added.
        global __package__
        __package__="graphAdapter.map_memory"
        worker_main(args.session,args.source_root,args.output_root)

if __name__=="__main__":main()
