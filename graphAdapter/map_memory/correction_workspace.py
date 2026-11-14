"""Pinned correction inputs; detached work never owns the active writer.

The caller keeps PinnedCorrectionJob alive until the independent workspace is
materialized. Expensive validation/copy belongs to the background process, not
freeze(). Installation validates the complete main lineage and uses an exact-parent CAS.
"""
if __package__ in (None,""):
    import sys
    from pathlib import Path as _Path
    _root=_Path(__file__).resolve().parents[3]
    sys.path[:0]=[str(_root/"src"),str(_root/"vendor_sources/EvoMemNav")]
    __package__="graphAdapter.map_memory"

from dataclasses import dataclass
import hashlib,json,threading
from pathlib import Path
from poseAdapter.interfaces.mapping import CorrectionSnapshot
from .storage.store import canonical,VersionUnavailable,IntegrityError

@dataclass(frozen=True)
class CorrectionJob:
    payload_json:bytes
    @property
    def record(self):return json.loads(self.payload_json)
    @property
    def digest(self):return hashlib.sha256(self.payload_json).hexdigest()

class PinnedCorrectionJob:
    def __init__(self,reader,job):self.reader=reader;self.job=job;self.owner_thread=threading.get_ident()
    def close(self):
        if threading.get_ident()!=self.owner_thread:raise RuntimeError('Correction source pin must close on its owning thread')
        if self.reader is not None:self.reader.close();self.reader=None
    def __enter__(self):return self
    def __exit__(self,*exc):self.close()


def freeze_correction_job(service,target):
    if not isinstance(target,CorrectionSnapshot):raise TypeError('CorrectionSnapshot required')
    if service.mapping_chart is None or service.pointer is None:raise VersionUnavailable('No published mapping chart')
    service.mapping_chart.propose_correction(target)
    latest=max(service.frames.values(),key=lambda row:row['capture_seq'])
    if target.frame_id!=latest['frame_uid'] or target.timestamp_ns>latest['sensor_timestamp_ns']:
        raise IntegrityError('Correction provenance is outside the frozen observation frontier')
    from .service import measured
    latest_measured=max((row['sensor_timestamp_ns'] for row in service.frames.values() if measured(row['pose_record'])),default=0)
    if target.timestamp_ns<latest_measured:
        raise VersionUnavailable('Correction target predates frozen measured contributions')
    base=service.pointer['snapshot_id'];reader=service.store.open_reader(base)
    try:
        if service.store._pointer()!=service.pointer:raise VersionUnavailable('Base advanced before correction input pin')
        from omegaconf import OmegaConf
        cfg=OmegaConf.to_container(service.cfg,resolve=True)
        cg_cfg=OmegaConf.to_container(service.cg_cfg,resolve=True)
        material=dict(schema_version=1,episode_uid=service.store.episode_uid,episode_instance=target.episode_instance,
            source_root=str(service.store.root),base_snapshot_id=base,base_cutoff=dict(reader.cutoff),
            target_provenance=target.to_record(),model_identity=service.model_identity,
            cfg=cfg,cg_cfg=cg_cfg,geometry_options=dict(service.geometry_options),
            correction_options=dict(service.correction_options),resource_limits=dict(service.resource_limits))
        return PinnedCorrectionJob(reader,CorrectionJob(canonical(material)))
    except BaseException:reader.close();raise


def materialize_correction_input(job,destination):
    if not isinstance(job,CorrectionJob):raise TypeError('Frozen CorrectionJob required')
    from .storage.final_snapshot import export_final
    from .storage.store import load_episode,_write_immutable
    data=job.record;destination=Path(destination).absolute()
    source=Path(data['source_root']).resolve()
    if destination.resolve().is_relative_to(source) or source.is_relative_to(destination.resolve()):
        raise IntegrityError('Detached workspace must not contain or be inside the active episode')
    result=export_final(data['source_root'],destination,revision=data['base_snapshot_id'])
    if result['source_snapshot_id']!=data['base_snapshot_id'] or result['cutoff']!=data['base_cutoff']:
        raise IntegrityError('Detached input exported another frontier')
    reader=load_episode(destination)
    try:
        if reader.identity['episode_uid']!=data['episode_uid'] or reader._graph['model_identity']!=data['model_identity']:
            raise IntegrityError('Detached episode/model identity differs')
        # Final snapshots retain detector blobs and their inline provenance. The
        # original CameraDetectionArchive additionally needs these small records.
        for uid,view in reader._graph['views'].items():
            detection=view.get('detection_record')
            if detection is not None:
                _write_immutable(destination,'detections/'+uid+'.meta.json',canonical(detection))
    finally:reader.close()
    _write_immutable(destination,'CORRECTION_INPUT.json',canonical(dict(job_sha256=job.digest,job=data)))
    return result



class DetachedWorkspaceSession:
    """One owned mutable workspace; reuse service/cache state only on its exact CURRENT."""
    def __init__(self):self.service=None;self.key=None;self.creations=0;self.reuses=0
    def acquire(self,job,destination,dataset):
        from omegaconf import OmegaConf
        from .service import MapMemoryService
        from .storage.store import EpisodeStore
        key=(job.digest,str(Path(destination).resolve()),dataset)
        if self.service is not None and key==self.key:
            if self.service.prepared is not None or self.service.store._pointer()!=self.service.pointer:
                raise IntegrityError('Retained workspace no longer matches its committed state')
            self.reuses+=1;return self.service
        self.close();data=job.record
        store=EpisodeStore(destination,data['episode_uid'],dataset=dataset,create=False)
        try:
            self.service=MapMemoryService(store,OmegaConf.create(data['cfg']),OmegaConf.create(data['cg_cfg']),
                models=None,model_identity=data['model_identity'],geometry_options=data['geometry_options'],
                correction_options=data['correction_options'],resource_limits=data['resource_limits'],cpu_contract=True)
        except BaseException:store.close();raise
        self.key=key;self.creations+=1;return self.service
    def release(self,job,destination):
        from .storage.store import _write_immutable
        from .storage.final_snapshot import plain
        expected=(job.digest,str(Path(destination).resolve()))
        if self.service is None or self.key[:2]!=expected:
            raise IntegrityError('Release does not identify the retained workspace')
        service=self.service;pointer=plain(service.pointer)
        if service.prepared is not None or service.store._pointer()!=service.pointer:
            raise IntegrityError('Cannot release uncommitted or stale retained state')
        self.close();audit=service.store.release_audit()
        if not audit['memory_closed']:raise IntegrityError('Workspace store did not close')
        result=dict(job_sha256=job.digest,target_provenance=job.record['target_provenance'],
            detached_snapshot=pointer,replayed_through=pointer['cutoff'],workspace_closed=True,
            release_audit=audit,detector_frames=0,installed_in_active_store=False)
        _write_immutable(Path(destination),'WORKSPACE_RELEASE.json',canonical(result))
        return result
    def close(self):
        if self.service is not None:self.service.store.close()
        self.service=None;self.key=None


def build_detached(job,destination,*,session=None):
    """Run the original correction implementation in an independent store.

    No main writer, simulator, pose estimator or perception model is constructed.
    Installation/tail catch-up are separate operations and are not implied here.
    """
    from omegaconf import OmegaConf
    from .service import MapMemoryService
    from .storage.store import EpisodeStore,load_episode,_write_immutable
    from .storage.final_snapshot import plain
    data=job.record;destination=Path(destination)
    materialize_correction_input(job,destination)
    reader=load_episode(destination)
    try:dataset=reader.identity['dataset']
    finally:reader.close()
    owner=session if session is not None else DetachedWorkspaceSession()
    try:
        service=owner.acquire(job,destination,dataset);store=service.store
        ready=service.prepare_correction(CorrectionSnapshot.from_record(data['target_provenance']),derivation_source=data['base_snapshot_id'])
        if ready['duplicate']:
            pointer=service.pointer
        else:
            pointer=service.publish_prepared(frame_uid=ready['frame_uid'],target_pose_map_version=ready['target_pose_map_version'])
        checked=store.open_reader()
        try:
            inspection=checked.verify()
            if dict(checked.cutoff)!=data['base_cutoff']:raise IntegrityError('Detached correction changed observation frontier')
            if set(checked._graph['views'])!=set(service.frames):raise IntegrityError('Detached correction lost observations')
        finally:checked.close()
        result=dict(schema_version=1,job_sha256=job.digest,source_base_snapshot_id=data['base_snapshot_id'],
            workspace_role='mutable_derived_work',seed_export_is_not_current_result=True,
            target_provenance=data['target_provenance'],replayed_through=dict(pointer['cutoff']),
            detached_snapshot=plain(pointer),inspection=inspection,installed_in_active_store=False,
            detector_frames=service.scene.model_frames)
        if result['detector_frames']!=0:raise IntegrityError('Detached correction reran perception')
        _write_immutable(destination,'CORRECTION_RESULT.json',canonical(result))
        return result
    except BaseException:
        owner.close();raise
    finally:
        if session is None:owner.close()


def validate_append_only_lineage(job,reader,tail):
    """Certify the exact immutable parent chain without re-reading image blobs."""
    from .storage.pages import read_revision
    data=job.record
    if reader.identity['episode_uid']!=data['episode_uid']:raise IntegrityError('Lineage episode differs')
    base=data['base_snapshot_id'];base_row=read_revision(reader.pages.db,base)
    base_context=json.loads(base_row[3]);sid=reader.snapshot_id;chain=[];seen=set()
    while sid!=base:
        if sid in seen or sid is None:raise VersionUnavailable('Correction base is not an ancestor')
        seen.add(sid);row=read_revision(reader.pages.db,sid);chain.append((sid,row));sid=row[0]
    chain.reverse();tail=list(tail)
    if len(chain)!=len(tail):raise VersionUnavailable('Current history is not explained by the complete append journal')
    expected_seq=data['base_cutoff']['capture_seq']
    for (sid,row),item in zip(chain,tail):
        packet=item.packet;expected_seq+=1
        if packet.episode_uid!=data['episode_uid'] or item.episode_instance!=data['episode_instance'] or packet.capture_seq!=expected_seq:
            raise IntegrityError('Tail identity/sequence differs from frozen source session')
        context=json.loads(row[3])
        if context!=base_context:raise VersionUnavailable('Another correction or derivation context changed the main history')
        public=dict(versions={'pose_map_version':base_context['version']},
            cutoff={'capture_seq':packet.capture_seq,'event_seq':packet.event_seq},
            episode_uid=data['episode_uid'],storage_codec='literal_history_v1')
        contract=hashlib.sha256(canonical(public)).hexdigest()
        # BundlePages binds EpisodeStore's source identity and public contract.
        expected_source=hashlib.sha256(canonical([contract,contract])).hexdigest()
        if expected_source!=row[4]:
            raise VersionUnavailable('Main revision does not correspond to this tail observation')
    return dict(base_snapshot_id=base,through_snapshot_id=reader.snapshot_id,appends=len(chain),
                cutoff=dict(reader.cutoff),target_provenance=data['target_provenance'])


def append_detached_tail(job,destination,tail,source_reader,*,append_journal=None,session=None):
    """Append only new frozen inputs to an already corrected private workspace.

    target_provenance is never rewritten. The reader must pin the source frames
    whose immutable RGB-D/camera data are being reused. No active CURRENT writes.
    """
    from omegaconf import OmegaConf
    from .async_admission import FrozenObservation
    from .service import MapMemoryService
    from .perception.scene import unpack_camera
    from .storage.store import EpisodeStore,_verify_ref,decode_arrays,_write_immutable
    from .storage.final_snapshot import plain
    data=job.record;destination=Path(destination);tail=list(tail)
    # Validate the entire main lineage, even on later incremental catch-up calls.
    journal=list(tail if append_journal is None else append_journal)
    lineage=validate_append_only_lineage(job,source_reader,journal)
    seed=json.loads((destination/'CORRECTION_INPUT.json').read_bytes())
    if seed['job_sha256']!=job.digest:raise IntegrityError('Workspace belongs to another correction job')
    if source_reader.identity['episode_uid']!=data['episode_uid'] or source_reader._graph['model_identity']!=data['model_identity']:
        raise IntegrityError('Tail source belongs to another episode/model')
    owner=session if session is not None else DetachedWorkspaceSession()
    try:
        service=owner.acquire(job,destination,source_reader.identity['dataset']);store=service.store
        if service.mapping_chart.episode_instance!=data['episode_instance']:
            raise IntegrityError('Detached chart session changed')
        expected_tail=[item for item in journal if item.packet.capture_seq>service.pointer['cutoff']['capture_seq']]
        if tail!=expected_tail:
            raise IntegrityError('Tail must equal the unprocessed suffix of the complete append journal')
        completed=[]
        for frozen in tail:
            if not isinstance(frozen,FrozenObservation) or frozen.episode_instance!=data['episode_instance']:
                raise IntegrityError('Tail requires the original frozen session inputs')
            packet=frozen.packet;record=packet.to_record()
            if packet.capture_seq!=service.pointer['cutoff']['capture_seq']+1:
                raise IntegrityError('Tail is not consecutive with detached frontier')
            view=source_reader.get_view(packet.frame_uid,include_images=True,include_depth=True)
            meta=view['capture']
            if canonical(plain({key:meta[key] for key in record}))!=canonical(record):
                raise IntegrityError('Tail packet differs from committed source facts')
            depth=view.get('depth') or {}
            values=dict(rgb=view['raw_rgb'],raw_depth=depth.get('raw_depth'),aligned_depth=depth.get('aligned_depth'),valid_mask=depth.get('valid_mask'))
            kwargs=dict(host_view=view.get('host_view'),host_transform=plain(meta.get('host_transform')))
            raw=store.archive_frame(record,**values,**kwargs)
            if raw['raw_signature']!=meta['raw_signature']:raise IntegrityError('Tail raw material changed identity')
            detection=view.get('detection_record')
            if detection is None:raise IntegrityError('Tail camera result is not ready; never recompute perception')
            arrays=decode_arrays(_verify_ref(source_reader.root,detection['blob']),detection['blob']['arrays'])
            service.camera[packet.frame_uid]=unpack_camera(arrays,detection['metadata'])
            ready=service.prepare_endpoint(packet,**values,**kwargs,committed_receipt=frozen.receipt,
                mapping_sample=frozen.mapping_sample,apply_mapping_correction=False)
            if ready['duplicate'] or ready['rebuild']:raise IntegrityError('Tail unexpectedly duplicated or rebuilt history')
            pointer=service.publish_prepared(frame_uid=packet.frame_uid,target_pose_map_version=ready['target_pose_map_version'])
            completed.append(dict(frame_uid=packet.frame_uid,snapshot_id=pointer['snapshot_id'],replayed_frames=ready['replayed_frames']))
        result=dict(job_sha256=job.digest,target_provenance=data['target_provenance'],
            replayed_through=dict(service.pointer['cutoff']),detached_snapshot=plain(service.pointer),
            appended=completed,source_lineage=lineage,installed_in_active_store=False,detector_frames=service.scene.model_frames)
        if result['detector_frames']!=0:raise IntegrityError('Tail recomputed perception')
        _write_immutable(destination,'tail-results/'+service.pointer['snapshot_id']+'.json',canonical(result))
        return result
    except BaseException:
        owner.close();raise
    finally:
        if session is None:owner.close()


def catch_up_detached(job,destination,input_path,*,session=None):
    """Process entry: reuse a corrected prefix and a pinned committed tail."""
    from .async_admission import FrozenObservation
    from .storage.store import load_episode
    from graphAdapter.observation_packet import ObservationPacket
    from poseAdapter.interfaces.mapping import MappingSample
    payload=json.loads(Path(input_path).read_bytes())
    if payload['job_sha256']!=job.digest:raise IntegrityError('Tail input belongs to another correction')
    from .tail_journal import frozen_from_record
    journal=[frozen_from_record(row) for row in payload['journal']]
    source=load_episode(job.record['source_root'],revision=payload['source_snapshot_id'])
    try:
        derived=load_episode(destination)
        try:cutoff=derived.cutoff['capture_seq']
        finally:derived.close()
        tail=[item for item in journal if item.packet.capture_seq>cutoff]
        result=append_detached_tail(job,destination,tail,source,append_journal=journal,session=session)
    finally:source.close()
    stage_detached_blobs(job,destination)
    return result


def _import_immutable_graph(graph,source_root,target_root):
    """Import only absent content; independent of either store's writer state."""
    from .storage.archive import owned_references,_verify_ref,_owned,sync_dir
    import os,shutil,uuid
    imported=0;reused=0
    for ref in owned_references(graph):
        target=_owned(target_root,ref['path'])
        if target.exists():_verify_ref(target_root,ref);reused+=1;continue
        source=_verify_ref(source_root,ref);target.parent.mkdir(parents=True,exist_ok=True)
        pending=target_root/'.pending';pending.mkdir(exist_ok=True)
        temporary=pending/(uuid.uuid4().hex+'.import')
        try:
            with source.open('rb') as a,temporary.open('xb') as b:
                shutil.copyfileobj(a,b,1024*1024);b.flush();os.fsync(b.fileno())
            # Verify the bytes actually copied before exposing an immutable name.
            temporary_ref=dict(ref,path=str(temporary.relative_to(target_root)))
            _verify_ref(target_root,temporary_ref)
            try:os.link(temporary,target)
            except FileExistsError:_verify_ref(target_root,ref)
            sync_dir(target.parent);imported+=1
        finally:temporary.unlink(missing_ok=True)
    return dict(imported_blobs=imported,reused_blobs=reused)


def stage_detached_blobs(job,destination):
    """Background-safe blob preparation. Never updates CURRENT or SQLite.

    Pins both stores against cleanup while copying. The receipt is informational:
    installation still checks the exact frontier and verifies immutable content.
    """
    from .storage.store import load_episode
    from .storage.final_snapshot import plain
    data=job.record;destination=Path(destination)
    seed=json.loads((destination/'CORRECTION_INPUT.json').read_bytes())
    if seed!={'job_sha256':job.digest,'job':data}:raise IntegrityError('Staging workspace belongs to another job')
    source_root=Path(data['source_root'])
    active=load_episode(source_root);derived=None
    try:
        derived=load_episode(destination)
        if active.identity!=derived.identity:raise IntegrityError('Staging episode identity differs')
        graph=plain(derived._graph)
        if graph['model_identity']!=data['model_identity']:raise IntegrityError('Staging model differs')
        result=_import_immutable_graph(graph,destination,source_root)
        return dict(result,job_sha256=job.digest,derived_snapshot_id=derived.snapshot_id,
            observed_active_snapshot_id=active.snapshot_id,published=False)
    finally:
        if derived is not None:derived.close()
        active.close()


def install_detached(service,job,destination,append_journal,*,fault=None):
    """Sole-writer adoption; no inference or geometric replay on this path.

    Caller serializes this operation with ordinary publication. Immutable blob
    import precedes the CURRENT CAS; failure may leave reusable unreferenced
    blobs, never a partially visible graph. This is not a scheduler API.
    """
    from .storage.store import load_episode
    from .storage.final_snapshot import plain
    from .storage.archive import owned_references,_verify_ref,_owned,sync_dir
    from .service import cross_revision_entities
    import os,shutil,uuid
    data=job.record;destination=Path(destination)
    if service.prepared is not None:raise VersionUnavailable('Ordinary prepared work must finish before detached installation')
    if service.tail_journal is not None:raise VersionUnavailable('Detach the completed tail journal before installing correction')
    if service.store.root.resolve()!=Path(data['source_root']).resolve():raise IntegrityError('Installation source root differs')
    seed=json.loads((destination/'CORRECTION_INPUT.json').read_bytes())
    result=json.loads((destination/'CORRECTION_RESULT.json').read_bytes())
    if seed!={'job_sha256':job.digest,'job':data} or result['job_sha256']!=job.digest or result['target_provenance']!=data['target_provenance']:
        raise IntegrityError('Detached result belongs to another job')
    current=service.store.open_reader();derived=None
    try:
        if service.pointer['snapshot_id']!=current.snapshot_id:raise VersionUnavailable('Service is not on the active installation base')
        lineage=validate_append_only_lineage(job,current,append_journal)
        derived=load_episode(destination);derived.verify(hashes=True,references=True)
        if dict(derived.cutoff)!=dict(current.cutoff):raise VersionUnavailable('Detached result has not caught up to CURRENT')
        if derived.identity!=current.identity:raise IntegrityError('Detached identity differs')
        graph=plain(derived._graph);live=plain(current._graph)
        target=CorrectionSnapshot.from_record(data['target_provenance'])
        if graph['versions']['pose_map_version']!=target.native_map_version or canonical(graph['pose_bindings'])!=canonical(target.bindings):
            raise IntegrityError('Detached result differs from the frozen correction target')
        if graph.get('mapping_state',{}).get('chart',{}).get('episode_instance')!=data['episode_instance']:
            raise IntegrityError('Detached chart belongs to another session')
        from omegaconf import OmegaConf
        for key,value in [('cfg',OmegaConf.to_container(service.cfg,resolve=True)),
                          ('cg_cfg',OmegaConf.to_container(service.cg_cfg,resolve=True)),
                          ('geometry_options',service.geometry_options),('correction_options',service.correction_options)]:
            if canonical(value)!=canonical(data[key]):raise IntegrityError('Configuration changed during correction: '+key)
        if graph['model_identity']!=service.model_identity:raise IntegrityError('Detached model identity differs')
        if set(graph['views'])!=set(live['views']):raise IntegrityError('Detached observation membership differs')
        for uid in live['views']:
            for key in ('frame_uid','capture_seq','env_step','source_event_seq','sensor_timestamp_ns','detection_record'):
                if canonical(graph['views'][uid].get(key))!=canonical(live['views'][uid].get(key)):
                    raise IntegrityError('Detached source view differs: '+uid+'/'+key)
        if canonical(derived.pages.lookup(('facts',)))!=canonical(current.pages.lookup(('facts',))):
            raise IntegrityError('Detached raw source references differ')
        if canonical(graph['edges'])!=canonical(live['edges']):raise IntegrityError('Detached execution edges differ')
        # Reconcile against CURRENT objects, including objects introduced while
        # correction ran. Private-workspace transition stubs are not authoritative.
        epoch=graph['scene_state']['epoch']
        if epoch!=service.epoch:
            entities=[x for x in graph['entities'] if x['epoch']==epoch]
            previous=[x for x in live['entities'] if x['epoch']==service.epoch]
            transitions=cross_revision_entities(previous,entities)
            stubs={(x['epoch'],x['id']):dict(x,attributes=None,pose_map_version=None,
                members=[],view_uids=[],source_revision=current.snapshot_id,
                status='historical' if x['status']=='active' else x['status']) for x in previous}
            for relation in transitions:stubs[(relation['epoch'],relation['src'])]['status']=relation['status']
            graph['entities']=list(stubs.values())+entities
            graph['aliases']=[x for x in graph['aliases'] if x['epoch']==epoch]+transitions
        copied=_import_immutable_graph(graph,destination,service.store.root)
        base=current.snapshot_id
        try:
            pointer=service.store.publish(graph,dict(derived.versions),dict(derived.cutoff),
                expected_parent_id=base,fault=fault)
        finally:
            actual=service.store._pointer()
            if actual!=service.pointer:
                service.store.current=actual;service._reload()
        return dict(snapshot_id=pointer['snapshot_id'],parent_snapshot_id=base,
            job_sha256=job.digest,source_lineage=lineage,cutoff=dict(pointer['cutoff']),versions=dict(pointer['versions']),
            **copied,installed_in_active_store=True)
    finally:
        if derived is not None:derived.close()
        current.close()


if __name__=="__main__":
    import argparse,os
    parser=argparse.ArgumentParser()
    parser.add_argument('--job',required=True);parser.add_argument('--out',required=True)
    modes=parser.add_mutually_exclusive_group()
    modes.add_argument('--stage-only',action='store_true')
    modes.add_argument('--tail-input')
    args=parser.parse_args()
    from .correction_runtime import require_correction_runtime
    require_correction_runtime()
    job=CorrectionJob(Path(args.job).read_bytes())
    if args.tail_input:
        result=catch_up_detached(job,args.out,args.tail_input)
        print(json.dumps(dict(job_sha256=job.digest,cutoff=result['replayed_through'],installed_in_active_store=False)))
    elif args.stage_only:
        print(json.dumps(stage_detached_blobs(job,args.out)))
    else:
        result=build_detached(job,args.out)
        print(json.dumps(dict(job_sha256=job.digest,detached_snapshot=result['detached_snapshot']['snapshot_id'],installed_in_active_store=False)))
