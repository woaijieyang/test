"""Reclaim a successful private compute map only after independent main-store verification."""
from pathlib import Path
import fcntl,json,os,shutil,uuid
from contextlib import ExitStack
from .storage.store import load_episode,canonical,IntegrityError,_write_immutable
from .storage.final_snapshot import plain,footprint
from .storage.archive import owned_references,_verify_ref,sync_dir

def reclaim_workspace(service,job,workspace,installation):
    workspace=Path(workspace).absolute();build=workspace.parent
    source=service.store.root.resolve()
    if workspace.name!='map' or workspace.resolve()!=workspace or build.resolve()!=build:
        raise IntegrityError('Only an owned real map leaf may be reclaimed')
    if workspace.is_relative_to(source) or source.is_relative_to(workspace):raise IntegrityError('Compute workspace overlaps main store')
    if Path(job.record['source_root']).resolve()!=source:raise IntegrityError('Reclaim source root differs')
    if installation.get('installed_in_active_store') is not True or installation.get('job_sha256')!=job.digest:
        raise IntegrityError('No successful matching installation receipt')
    if (build/'job.json').read_bytes()!=job.payload_json:raise IntegrityError('Build owner job differs')
    seed=json.loads((workspace/'CORRECTION_INPUT.json').read_bytes())
    release=json.loads((workspace/'WORKSPACE_RELEASE.json').read_bytes())
    if seed!={'job_sha256':job.digest,'job':job.record} or release.get('job_sha256')!=job.digest or release.get('workspace_closed')is not True:
        raise IntegrityError('Missing matching workspace release')
    if json.loads((workspace/'CURRENT.json').read_bytes())!=release['detached_snapshot']:
        raise IntegrityError('Released workspace advanced afterward')
    if any(p.is_symlink() for p in workspace.rglob('*')):raise IntegrityError('Compute workspace contains symlinks')
    main=service.store.open_reader(installation['snapshot_id']);derived=None
    try:
        derived=load_episode(workspace)
        if dict(main.cutoff)!=dict(derived.cutoff) or dict(main.versions)!=dict(derived.versions):
            raise IntegrityError('Installed and private map frontiers differ')
        if canonical(main.pages.lookup(('facts',)))!=canonical(derived.pages.lookup(('facts',))):
            raise IntegrityError('Original observation evidence differs')
        checks=main.verify(hashes=True,references=True)
        graph=plain(derived._graph);installed_graph=plain(main._graph)
        for key in set(graph)|set(installed_graph):
            if key not in ('entities','aliases') and canonical(graph.get(key))!=canonical(installed_graph.get(key)):
                raise IntegrityError('Installed graph differs from released workspace: '+key)
        epoch=graph['scene_state']['epoch']
        for key in ('entities','aliases'):
            expected=[row for row in graph[key] if row['epoch']==epoch]
            actual=[row for row in installed_graph[key] if row['epoch']==epoch]
            if canonical(expected)!=canonical(actual):raise IntegrityError('Installed active object provenance differs')
        if set(graph['views'])!=set(main._graph['views']):raise IntegrityError('Main map lost private observations')
        # These bytes must all survive independently of the soon-to-be-removed workspace.
        refs=owned_references(graph)
        for ref in refs:_verify_ref(source,ref)
        sid=derived.snapshot_id
    finally:
        if derived is not None:derived.close()
        main.close()
    sizes=footprint(workspace)
    with ExitStack() as held:
        for name in ('writer.lock','pins.lock'):
            handle=held.enter_context((workspace/name).open('r+b'))
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if json.loads((workspace/'CURRENT.json').read_bytes())!=release['detached_snapshot']:
            raise IntegrityError('Workspace changed before reclamation')
        quarantine=build/('.reclaim-'+uuid.uuid4().hex)
        if quarantine.parent.resolve()!=build or quarantine.exists():raise IntegrityError('Invalid reclaim destination')
        receipt=dict(job_sha256=job.digest,source_root=str(source),installed_snapshot_id=installation['snapshot_id'],
            private_snapshot_id=sid,private_workspace=str(workspace),quarantine=str(quarantine),
            original_maps_retained=True,verified_main=checks,independent_reference_files=len(refs),footprint=sizes)
        _write_immutable(build,'RECLAIM_PREPARED.json',canonical(receipt))
        os.rename(workspace,quarantine);sync_dir(build)
        shutil.rmtree(quarantine);sync_dir(build)
        receipt['status']='RECLAIMED_PRIVATE_COMPUTE_MAP'
        _write_immutable(build,'RECLAIMED.json',canonical(receipt))
    return receipt
