"""Owned episode retention and recoverable cleanup; not kernel quota enforcement."""
from __future__ import annotations
from contextlib import contextmanager, ExitStack
from pathlib import Path
import fcntl
import gzip
import hashlib
import itertools
import json
import os
import re
import stat
import tarfile
import uuid

MODES = {"ordinary", "preview_only", "graph_metadata_only", "queryable", "rebuildable", "audit_full"}
FIELDS = {
    "reset": ("task_key","state_evaluator_only"),
    "model_input": ("task_key", "call_id", "frame", "prompt", "input_ids", "processed_image_shape", "processed_image_sha256", "generation", "stop_str", "sep2"),
    "model_call": ("task_key", "call_id", "frame", "output_ids", "raw_decoded_output", "normalized_output"),
    "primitive_action": ("task_key", "step", "last_call_id", "action", "done", "stop_source", "before_evaluator_only", "after_evaluator_only"),
    "terminal": ("task_key", "steps", "native_metrics", "model_calls", "termination_reason", "stop_source"),
    "attempt_aborted": ("steps", "reason", "executed_action", "cancelled_actions"),
}

class LifecycleError(RuntimeError):
    pass

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()

def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024**2), b""):
            h.update(block)
    return h.hexdigest()

def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def atomic_json(path, value):
    path = Path(path)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".pending")
    with tmp.open("xb") as stream:
        stream.write(canonical(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)
    sync_dir(path.parent)

def segment(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value):
        raise LifecycleError("Unsafe identity segment")
    return value

def inside(root, path):
    root, path = Path(root).absolute(), Path(path).absolute()
    if path != root and root not in path.parents:
        raise LifecycleError("Path outside owned root")
    if root.resolve() != root or path.resolve() != path:
        raise LifecycleError("Symlink or noncanonical owned path")
    return path

def regular_tree(root):
    root = Path(root)
    for folder, dirs, files in os.walk(root, followlinks=False):
        for name in dirs:
            path = Path(folder) / name
            if path.is_symlink() or path.stat().st_dev != root.stat().st_dev:
                raise LifecycleError("Linked or mounted directory")
        for name in sorted(files):
            path = inside(root, Path(folder) / name)
            s = path.lstat()
            if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1:
                raise LifecycleError("Nonregular or aliased file: " + str(path))
            yield path

def usage(root):
    logical = allocated = count = 0
    for p in regular_tree(root):
        s = p.stat()
        logical += s.st_size
        allocated += s.st_blocks * 512
        count += 1
    return dict(logical_bytes=logical, allocated_bytes=allocated, files=count)

def process_identity(pid):
    try:
        tail = Path(f"/proc/{int(pid)}/stat").read_text().rsplit(")", 1)[1].split()
        return dict(pid=int(pid), starttime=tail[19])
    except FileNotFoundError:
        return None

def assert_owners_closed(owners):
    for owner in owners:
        if process_identity(owner["pid"]) == owner:
            raise LifecycleError("A registered producer is still alive")

def assert_no_open_files(root, owners=()):
    """Inspect registered producers and this finalizer, never unrelated projects.

    Producers must be identity-checked closed first. Protected namespaces cannot
    inspect arbitrary same-uid external processes; do not claim a machine-wide
    descriptor audit. A sole-owner work tree and leases are the contract here.
    """
    root = str(Path(root).absolute())
    processes = {os.getpid(), *(int(owner['pid']) for owner in owners)}
    for pid in processes:
        process = Path('/proc') / str(pid)
        try:
            if process.stat().st_uid != os.geteuid():
                continue
            descriptors = list((process / "fd").iterdir())
        except FileNotFoundError:
            continue
        except PermissionError as error:
            raise LifecycleError("Cannot verify producer descriptors") from error
        for descriptor in descriptors:
            try:
                target = os.readlink(descriptor).removesuffix(" (deleted)")
            except FileNotFoundError:
                continue
            if target == root or target.startswith(root + "/"):
                raise LifecycleError("An owned file/directory is still open")

@contextmanager
def exclusive(path):
    with Path(path).open("a+b") as guard:
        try:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise LifecycleError("Active finalizer or evidence lease") from error
        yield

def json_rows(path, *, max_row_bytes=8*1024**2, max_bytes=512*1024**2):
    opener = gzip.open if str(path).endswith(".gz") else open
    total = 0
    with opener(path, "rb") as stream:
        while True:
            line = stream.readline(max_row_bytes + 1)
            if not line:
                break
            total += len(line)
            if len(line) > max_row_bytes or total > max_bytes or not line.endswith(b"\n"):
                raise LifecycleError("Evidence bounds/partial JSONL exceeded")
            yield json.loads(line)

def compress_jsonl(source, target, *, max_raw, max_compressed, max_row=8*1024**2):
    """Preserve every byte; exceeding a bound fails without truncating source."""
    target = Path(target)
    temporary = target.with_name(target.name + ".pending")
    if temporary.exists():
        if temporary.is_symlink() or temporary.stat().st_nlink != 1:
            raise LifecycleError("Unsafe interrupted compression")
        temporary.unlink()
    h = hashlib.sha256()
    count = total = 0
    with Path(source).open("rb") as src, temporary.open("xb") as dst:
        with gzip.GzipFile(fileobj=BoundedWriter(dst,max_compressed), mode="wb", mtime=0, compresslevel=6) as zipped:
            while True:
                line = src.readline(max_row + 1)
                if not line:
                    break
                total += len(line)
                if len(line) > max_row or total > max_raw or not line.endswith(b"\n"):
                    raise LifecycleError("Trace limit/partial write: source retained")
                json.loads(line)
                h.update(line)
                zipped.write(line)
                zipped.flush()
                if dst.tell() > max_compressed:
                    raise LifecycleError("Compressed trace limit: source retained")
                count += 1
        dst.flush()
        os.fsync(dst.fileno())
    if temporary.stat().st_size > max_compressed:
        raise LifecycleError("Compressed trace bound exceeded")
    restored = hashlib.sha256()
    with gzip.open(temporary, "rb") as stream:
        for block in iter(lambda: stream.read(1024**2), b""):
            restored.update(block)
    if restored.hexdigest() != h.hexdigest():
        raise LifecycleError("Compression roundtrip mismatch")
    os.replace(temporary, target)
    sync_dir(target.parent)
    return dict(rows=count, raw_bytes=total, raw_sha256=h.hexdigest(), compressed_bytes=target.stat().st_size, sha256=sha(target))

def business_rows(path,*,endpoint_schema=False):
    for row in json_rows(path):
        kind = row.get("kind")
        if kind not in FIELDS:
            continue
        if endpoint_schema and kind in ('reset','primitive_action'):
            keys=['state_evaluator_only']if kind=='reset'else['before_evaluator_only','after_evaluator_only']
            for key in keys:
                state=row.get(key)
                if not isinstance(state,dict)or not {'position','rotation_xyzw','elapsed_steps','episode_over','collided','endpoint_sensor'}<=set(state):
                    raise LifecycleError('Missing production endpoint state: '+key)
                sensor=state['endpoint_sensor']
                if not isinstance(sensor,dict)or any(not isinstance(sensor.get(k),str)or re.fullmatch('[0-9a-f]{64}',sensor[k])is None for k in ['rgb_sha256','depth_sha256']):
                    raise LifecycleError('Missing production endpoint RGB-D hash')
        result = dict(kind=kind, values={k: row.get(k) for k in FIELDS[kind]})
        if kind == "model_input":
            result["images"] = [{k: ref.get(k) for k in ("pixel_sha256", "size", "mode")} for ref in row.get("images", [])]
        yield result

def compare_traces(left, right, *, endpoint_schema=False):
    count=0;terminal=False
    try:
        for a,b in itertools.zip_longest(business_rows(left,endpoint_schema=endpoint_schema),business_rows(right,endpoint_schema=endpoint_schema)):
            if a!=b:return dict(equal=False,first_difference=count,compared_events=count)
            terminal=a['kind']in('terminal','attempt_aborted');count+=1
    except LifecycleError as error:
        return dict(equal=False,first_difference=count,compared_events=count,schema_error=str(error))
    return dict(equal=True,compared_events=count,terminal_present=terminal)

def verify_host_images(trace, source_root):
    from PIL import Image
    seen = set()
    for row in json_rows(trace):
        for ref in row.get("images", []):
            key = (ref["path"], ref["pixel_sha256"])
            if key in seen:
                continue
            path = inside(source_root, Path(source_root) / ref["path"])
            with Image.open(path) as image:
                actual = hashlib.sha256(image.mode.encode() + str(image.size).encode() + image.tobytes()).hexdigest()
                if (actual, list(image.size), image.mode) != (ref["pixel_sha256"], ref["size"], ref["mode"]):
                    raise LifecycleError("Host image pixels differ")
            seen.add(key)
    return len(seen)

def memory_capability(root, mode):
    """Read actual graph/image/rebuild inputs; no PNG-as-map declaration."""
    from .store import load_episode
    reader = load_episode(root, cache_bytes=0)
    try:
        result = reader.verify(hashes=True, references=True)
        images = rebuild_sources = 0
        for uid, view in reader._graph["views"].items():
            record = reader.get_view(uid, include_images=True, include_depth=True)
            if record.get("raw_rgb") is None:
                raise LifecycleError("Queryable view has no readable RGB")
            images += 1
            if mode in ("rebuildable", "audit_full") and view.get("geometry_fused"):
                capture = record["capture"]
                depths = record.get("depth", {})
                if not all(k in depths for k in ("aligned_depth", "valid_mask")):
                    raise LifecycleError("Missing exact fusion source")
                if capture.get("K") is None or capture.get("T_base_camera") is None:
                    raise LifecycleError("Missing calibration/mount binding")
                if view.get("pose_map_version") != reader.versions["pose_map_version"]:
                    raise LifecycleError("Mixed keyframe pose revision")
                rebuild_sources += 1
        return dict(mode=mode, snapshot_id=reader.snapshot_id, images=images, rebuild_sources=rebuild_sources, verification=result)
    finally:
        reader.close()

def pack_tree(source, target, *, max_bytes):
    """Stream regular files; verify every payload before publishing."""
    target = Path(target)
    pending = target.with_name(target.name + ".pending")
    if pending.exists():
        if pending.is_symlink() or pending.stat().st_nlink != 1:
            raise LifecycleError("Unsafe interrupted package")
        pending.unlink()
    expected = set()
    with pending.open("xb") as stream:
        with tarfile.open(fileobj=BoundedWriter(stream,max_bytes), mode="w|gz", format=tarfile.PAX_FORMAT) as tar:
            for path in regular_tree(source):
                relative = str(path.relative_to(source))
                expected.add(relative)
                info = tar.gettarinfo(str(path), arcname=relative)
                with path.open("rb") as data:
                    tar.addfile(info, data)
                if stream.tell() > max_bytes:
                    raise LifecycleError("Diagnostic archive exceeds sealed bound")
        stream.flush()
        os.fsync(stream.fileno())
    if pending.stat().st_size > max_bytes:
        raise LifecycleError("Diagnostic archive exceeds sealed bound")
    with tarfile.open(pending, "r|gz") as tar:
        for entry in tar:
            if entry.name not in expected or not entry.isfile():
                raise LifecycleError("Unexpected/duplicate package member")
            expected.remove(entry.name)
            original = inside(source, Path(source) / entry.name)
            data = tar.extractfile(entry)
            if data is None or original.stat().st_size != entry.size:
                raise LifecycleError("Package member size mismatch")
            h = hashlib.sha256()
            for block in iter(lambda: data.read(1024**2), b""):
                h.update(block)
            if h.hexdigest() != sha(original):
                raise LifecycleError("Package source mismatch")
    if expected:
        raise LifecycleError("Incomplete package")
    os.replace(pending, target)
    sync_dir(target.parent)
    return dict(sha256=sha(target), compressed_bytes=target.stat().st_size, expanded_bytes=usage(source)["logical_bytes"])

def unpack_tree(archive, target, *, max_expanded, expected_sha256, emergency_bytes=0):
    """Caller reserves source+expanded coexistence; partial target is never reused."""
    if sha(archive) != expected_sha256:
        raise LifecycleError("Archive checksum mismatch")
    target = Path(target).absolute()
    if target.resolve() != target:
        raise LifecycleError("Noncanonical extraction workspace")
    if type(emergency_bytes)is not int or emergency_bytes<0:raise LifecycleError('Invalid emergency bytes')
    existing=target.parent
    while not existing.exists():existing=existing.parent
    fs=os.statvfs(existing)
    if fs.f_bavail*fs.f_frsize<max_expanded+emergency_bytes:
        raise LifecycleError('Insufficient physical source/target coexistence space')
    target.mkdir(parents=True, exist_ok=False)
    total = 0
    with tarfile.open(archive, "r|gz") as tar:
        for entry in tar:
            if not entry.isfile() or entry.size < 0:
                raise LifecycleError("Nonregular archive entry")
            path = inside(target, target / entry.name)
            total += entry.size
            if total > max_expanded:
                raise LifecycleError("Expanded workspace bound exceeded")
            path.parent.mkdir(parents=True, exist_ok=True)
            data = tar.extractfile(entry)
            with path.open("xb") as stream:
                remaining = entry.size
                while remaining:
                    block = data.read(min(1024**2, remaining))
                    if not block:
                        raise LifecycleError("Partial archive entry")
                    stream.write(block)
                    remaining -= len(block)
                stream.flush()
                os.fsync(stream.fileno())
    return dict(expanded_bytes=total, archive_bytes=Path(archive).stat().st_size, source_plus_target_bytes=total + Path(archive).stat().st_size)

class EpisodeLifecycle:
    """One presealed identity/two sides. Never adopts preexisting work trees."""
    @classmethod
    def create_run(cls, root, plan):
        root = Path(root).absolute()
        if root.resolve() != root or Path(__file__).resolve().parents[4]/"outputs/graph_memory" not in root.parents:
            raise LifecycleError("Run must be a new canonical case graph_memory output")
        entries = plan.get("entries", [])
        if not entries or len({x["key"] for x in entries}) != len(entries):
            raise LifecycleError("Unique preselected entries required")
        for item in entries:
            segment(item["key"])
            if item["mode"] not in MODES or not isinstance(item.get("member"), list):
                raise LifecycleError("Explicit member and retention mode required")
            if any(mode not in MODES for mode in item.get('mode_by_side',{}).values()):
                raise LifecycleError('Unknown side retention mode')
        roles=plan.get('owner_roles')
        if not isinstance(roles,list) or not roles or len(set(roles))!=len(roles):
            raise LifecycleError('Nonempty presealed owner roles required')
        for role in roles:segment(role)
        components=plan.get('owner_components',{})
        if set(components)!=set(roles) or any(v not in {'file_owner','host_trace','memory','pose','pose_provider'}for v in components.values()):
            raise LifecycleError('Explicit owner component types required')
        for key in ("max_trace_raw_bytes", "max_trace_compressed_bytes", "max_diagnostic_bytes", "max_expanded_bytes", "max_ordinary_retained_bytes", "max_summary_bytes"):
            if type(plan.get(key)) is not int or plan[key] <= 0:
                raise LifecycleError("Positive sealed byte bounds required")
        root.mkdir(parents=True, exist_ok=False)
        atomic_json(root / "retention_plan.json", plan)
        return sha(root / "retention_plan.json")

    def __init__(self, root, key, side, attempt, *, plan_sha256):
        self.root = Path(root).absolute()
        self.key, self.side, self.attempt = map(segment, (key, side, attempt))
        if self.side not in ("control", "shadow"):
            raise LifecycleError("Unknown side")
        self.plan_sha = plan_sha256
        if sha(self.root / "retention_plan.json") != plan_sha256:
            raise LifecycleError("Retention plan drift")
        self.plan = json.loads((self.root / "retention_plan.json").read_bytes())
        self.entry = next((x for x in self.plan["entries"] if x["key"] == key), None)
        if self.entry is None:
            raise LifecycleError("Episode absent from presealed plan")
        self.work = inside(self.root, self.root / "work" / key / side / attempt)
        self.result = inside(self.root, self.root / "results" / key / side / attempt)
        self.identity = dict(plan_sha256=plan_sha256, key=key, side=side, attempt=attempt, member=self.entry["member"])

    def create_work(self):
        self.result.parent.mkdir(parents=True,exist_ok=True)
        maximum=self.plan.get('max_attempts_per_side',2)
        if type(maximum)is not int or maximum<1:raise LifecycleError('Positive bounded attempts required')
        with exclusive(self.result.parent/'attempts.lock'):
            if self.result.exists():raise FileExistsError(str(self.result))
            if sum(path.is_dir()for path in self.result.parent.iterdir())>=maximum:
                raise LifecycleError('Presealed attempt count exhausted;failed attempts retained')
            self.work.mkdir(parents=True, exist_ok=False)
            self.result.mkdir(parents=True, exist_ok=False)
            atomic_json(self.work / ".owned.json", self.identity)
            atomic_json(self.result / "state.json", dict(state="ACTIVE", identity=self.identity))
        return self.work

    def _state(self):
        row = json.loads((self.result / "state.json").read_bytes())
        if row["identity"] != self.identity:
            raise LifecycleError("State belongs to another attempt")
        return row

    def _owned(self):
        inside(self.root, self.work)
        if json.loads((self.work / ".owned.json").read_bytes()) != self.identity:
            raise LifecycleError("Work owner mismatch")

    @contextmanager
    def lease(self):
        with (self.result / "lease.lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_SH)
            if self._state()["state"] != "ACTIVE":
                raise LifecycleError("Source frozen; read retained package instead")
            yield self.work

    def _check_release(self, release):
        if any(release.get(k) is not True for k in ("consumers_joined", "native_closed", "memory_closed")):
            raise LifecycleError("Producer close/consumer completion unconfirmed")
        if release.get("pins") != 0 or release.get("leases") != 0:
            raise LifecycleError("Active pin/lease")
        caches = release.get("cache_entries")
        if not isinstance(caches, dict) or any(v != 0 for v in caches.values()):
            raise LifecycleError("Live episode cache")
        if "owners" not in release:
            raise LifecycleError("Explicit producer identities required")
        assert_owners_closed(release["owners"])
        verify_session_receipts(self,release.get('session_receipts'))

    def seal(self, *, trace, image_root, summary, release, memory=None, preview=None, graph_metadata=None, evidence_streams=None, fault=None):
        """Publish bounded terminal evidence, never delete during this step."""
        with exclusive(self.result / "lease.lock"):
            self._owned()
            if self._state()["state"] != "ACTIVE":
                raise LifecycleError("Attempt already sealed or deleting")
            self._check_release(release)
            assert_no_open_files(self.work, release["owners"])
            trace = inside(self.work, trace)
            image_root = inside(self.work, image_root)
            if max(len(canonical(summary)),len(canonical(release))) > self.plan["max_summary_bytes"]:
                raise LifecycleError("Summary exceeds sealed bound")
            before = usage(self.work)
            for row in json_rows(trace):
                if row.get("kind") == "reset":
                    if list(row.get("episode_scope", {}).get("member", [])) != self.entry["member"]:
                        raise LifecycleError("Trace member differs from sealed plan")
                    break
            else:
                raise LifecycleError("No reset identity in trace")
            verified_images = verify_host_images(trace, image_root)
            compression = compress_jsonl(trace, self.result / "trace.jsonl.gz",
                max_raw=self.plan["max_trace_raw_bytes"], max_compressed=self.plan["max_trace_compressed_bytes"])
            trace_audit = inspect_trace(self.result / "trace.jsonl.gz")
            streams = {}
            stream_sources = dict(evidence_streams or {})
            if self.entry.get('requires_geometry_evidence') and self.side=='shadow':
                if not {'observation_packets','flow','map_commits'}<=set(stream_sources):
                    raise LifecycleError('Per-frame source/snapshot evidence missing')
            allowed=set(self.entry.get('allowed_evidence_streams',['observation_packets','flow','map_commits','memory_history']))
            if not set(stream_sources)<=allowed:raise LifecycleError('Unsealed evidence stream name')
            for name,path in stream_sources.items():
                segment(name)
                if name in {'trace','materials'}:raise LifecycleError('Reserved evidence stream name')
                source=inside(self.work,path)
                streams[name]=compress_jsonl(source,self.result/(name+'.jsonl.gz'),
                    max_raw=self.plan['max_trace_raw_bytes'],max_compressed=self.plan['max_trace_compressed_bytes'])
            if self.plan.get('stage')=='002' and self.side=='shadow' and 'flow' in streams:
                from .decision_reads import seal_decision_reads
                if {'object_reads','approach_reads','evo_reads'} & stream_sources.keys():
                    raise LifecycleError('Reserved decision evidence stream')
                streams.update(seal_decision_reads(memory,self.work,self.result,self.result/'flow.jsonl.gz',self.plan))
            final_map_receipt=None
            if self.side=='shadow'and self.plan.get('final_map_policy')is not None:
                from .final_snapshot import retain_final_map,requires_final_map
                retain_this_map=requires_final_map(self.plan,self.entry)
                if not retain_this_map:
                    final_map_receipt=None
                elif memory is not None and(Path(memory)/'CURRENT.json').is_file():
                    final_map_receipt=retain_final_map(memory,self.work,self.result,self.identity,
                        max_compressed=self.plan['max_final_map_bytes'],max_expanded=self.plan['max_final_map_expanded_bytes'])
                elif summary.get('status')=='failed':
                    final_map_receipt=dict(status='NO_COMMITTED_MAP',identity=self.identity)
                    atomic_json(self.result/'final-map.json',final_map_receipt)
                else:raise LifecycleError('Final map missing; original work preserved')
            mode, capabilities, qualification = self.entry.get("mode_by_side",{}).get(self.side,self.entry["mode"]), [], {}
            if mode == "preview_only":
                from PIL import Image
                path = inside(self.work, preview)
                with Image.open(path) as image:
                    image.verify()
                if path.stat().st_size > self.plan["max_diagnostic_bytes"]:
                    raise LifecycleError("Preview bound")
                with path.open("rb") as src, (self.result / "preview.png").open("wb") as dst:
                    for block in iter(lambda: src.read(1024**2), b""):
                        dst.write(block)
                    dst.flush()
                    os.fsync(dst.fileno())
                capabilities = [mode]
            elif mode == "graph_metadata_only":
                if graph_metadata is None:
                    if memory is None:raise LifecycleError('Actual memory or metadata source required')
                    path=self.result/'graph.json'
                    export_graph_metadata(inside(self.work,memory),path)
                else:path = inside(self.work, graph_metadata)
                if path.stat().st_size > self.plan["max_diagnostic_bytes"]:
                    raise LifecycleError("Metadata bound")
                metadata = json.loads(path.read_bytes())
                if (not all(k in metadata for k in ("nodes", "edges", "revision"))
                    or not isinstance(metadata['nodes'],(list,dict))or not isinstance(metadata['edges'],list)
                    or not isinstance(metadata['revision'],str)or not metadata['revision']):
                    raise LifecycleError("Graph metadata incomplete")
                if path!=self.result/'graph.json':atomic_json(self.result / "graph.json", metadata)
                capabilities = [mode]
            elif mode in ("queryable", "rebuildable", "audit_full"):
                memory = inside(self.work, memory)
                qualification = memory_capability(memory, mode)
                if mode == "audit_full":
                    qualification['audit_inputs']=verify_audit_full_inputs(self.work,memory,
                        expected_source_sha256=self.entry.get('evidence_source_sha256',self.plan.get('evidence_source_sha256')))
                qualification["package"] = pack_tree(self.work, self.result / "memory.tar.gz", max_bytes=self.plan["max_diagnostic_bytes"])
                if qualification['package']['expanded_bytes']>self.plan['max_expanded_bytes']:
                    raise LifecycleError('Diagnostic cannot be restored within sealed expanded bound')
                qualification["memory_relative"] = str(memory.relative_to(self.work))
                capabilities = ["graph_metadata_only", "queryable"]
                if mode in ("rebuildable", "audit_full"):
                    capabilities.append("rebuildable")
                if mode == "audit_full":
                    capabilities.append("audit_full")
            if final_map_receipt is not None:
                qualification['final_map']=final_map_receipt
                if final_map_receipt['status']=='VERIFIED_FINAL_MAP_BEFORE_COMPUTE_RELEASE':
                    capabilities=sorted(set(capabilities)|{'final_snapshot','queryable'})
            inventory = self.result / "materials.jsonl"
            with inventory.open("wb") as stream:
                for path in regular_tree(self.work):
                    if path == self.work / ".owned.json":
                        continue
                    s = path.stat()
                    stream.write(canonical(dict(path=str(path.relative_to(self.work)), bytes=s.st_size,
                        allocated_bytes=s.st_blocks*512, inode=s.st_ino, device=s.st_dev, sha256=sha(path))) + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
            materials = compress_jsonl(inventory, self.result / "materials.jsonl.gz",
                max_raw=self.plan["max_trace_raw_bytes"], max_compressed=self.plan["max_trace_compressed_bytes"])
            inventory.unlink()
            artifact_names=['trace.jsonl.gz','materials.jsonl.gz']+[name+'.jsonl.gz'for name in streams]
            artifact_names+=[name for name in ('preview.png','graph.json','memory.tar.gz','final-map.tar.gz','final-map.json','final-map-cold-read.json','final-map-cold-read.log','final-map-temporary-release.json')if(self.result/name).exists()]
            artifacts={name:dict(sha256=sha(self.result/name),bytes=(self.result/name).stat().st_size)for name in artifact_names}
            receipt = dict(retention_schema_version=2,retained_artifacts=artifacts,identity=self.identity, summary=summary, release=release, capabilities=capabilities,
                qualification=qualification, trace=compression, trace_audit=trace_audit, evidence_streams=streams, materials=materials, verified_host_images=verified_images,
                before=before, open_file_audit_scope="registered exited producer identities and finalizer; leases guard managed readers; not unrelated machine processes", kernel_quota_enforced=False)
            if self.plan.get('stage')=='002' and self.side=='shadow' and 'flow' in streams:
                receipt['object_read_contract']='pinned-object-reads-v1'
                receipt['approach_read_contract']='pinned-approach-reads-v1'
            prospective=usage(self.result)['logical_bytes']+len(canonical(receipt))+4096
            terminal_bound=(self.plan['max_ordinary_retained_bytes']if mode=='ordinary'else
                            self.plan['max_diagnostic_bytes']+self.plan['max_ordinary_retained_bytes'])
            if final_map_receipt is not None and final_map_receipt['status']=='VERIFIED_FINAL_MAP_BEFORE_COMPUTE_RELEASE':terminal_bound+=self.plan['max_final_map_bytes']
            if prospective>terminal_bound:raise LifecycleError('Retained episode bound exceeded;source preserved')
            atomic_json(self.result / "retention.json", receipt)
            if fault:
                fault("before_sealed")
            atomic_json(self.result / "state.json", dict(state="SEALED", identity=self.identity))
            return receipt

    def finalize(self, pair_receipt, *, fault=None):
        with exclusive(self.result / "lease.lock"):
            state_row = self._state()
            state = state_row["state"]
            receipt = json.loads((self.result / "retention.json").read_bytes())
            if state == "DELETED":
                return json.loads((self.result / "finalization.json").read_bytes())
            if state not in ("SEALED", "DELETING"):
                raise LifecycleError("No published retained evidence")
            expected = pair_receipt.get("sides", {}).get(self.side, {})
            if (pair_receipt.get("key") != self.key or pair_receipt.get("plan_sha256") != self.plan_sha
                or expected.get("attempt") != self.attempt or expected.get("retention_sha256") != sha(self.result / "retention.json")
                or pair_receipt.get("audit_complete") is not True):
                raise LifecycleError("Independent paired audit missing or wrong attempt")
            for name, description in (("trace.jsonl.gz", receipt["trace"]), ("materials.jsonl.gz", receipt["materials"])):
                if sha(self.result / name) != description["sha256"]:
                    raise LifecycleError("Retained evidence corrupted")
            for name,description in receipt.get('evidence_streams',{}).items():
                if sha(self.result/(name+'.jsonl.gz'))!=description['sha256']:
                    raise LifecycleError('Retained per-frame evidence corrupted')
            package = receipt["qualification"].get("package")
            if package and sha(self.result / "memory.tar.gz") != package["sha256"]:
                raise LifecycleError("Retained diagnostic corrupted")
            verify_retained_artifacts(self.result,receipt)
            if self.side=='shadow'and self.plan.get('final_map_policy')is not None:
                from .final_snapshot import verify_retained_final_map,requires_final_map
                if requires_final_map(self.plan,self.entry):verify_retained_final_map(self.result,receipt,self.identity)
            self._check_release(receipt["release"])
            free_before = state_row.get("filesystem_free_before")
            if self.work.exists():
                if state == "DELETING" and not any(self.work.iterdir()):
                    # Crash after final marker removal, before rmdir.
                    self.work.rmdir()
                else:
                    self._owned()
                    assert_no_open_files(self.work, receipt["release"]["owners"])
                    with ExitStack() as pins:
                        for name in ("pins.lock", "writer.lock", "page-writer.lock"):
                            for path in self.work.rglob(name):
                                pins.enter_context(exclusive(path))
                        expected_paths = set()
                        for row in json_rows(self.result / "materials.jsonl.gz"):
                            expected_paths.add(row["path"])
                            path = inside(self.work, self.work / row["path"])
                            if not path.exists():
                                if state != "DELETING":
                                    raise LifecycleError("Source vanished before deletion authorization")
                                continue
                            s = path.lstat()
                            if (s.st_ino, s.st_dev, s.st_size, s.st_nlink) != (row["inode"], row["device"], row["bytes"], 1) or sha(path) != row["sha256"]:
                                raise LifecycleError("Material changed after audit")
                        for path in regular_tree(self.work):
                            if path != self.work / ".owned.json" and str(path.relative_to(self.work)) not in expected_paths:
                                raise LifecycleError("Unregistered late material")
                        if free_before is None:
                            fs = os.statvfs(self.work)
                            free_before = fs.f_bavail * fs.f_frsize
                        atomic_json(self.result / "state.json", dict(state="DELETING", identity=self.identity, filesystem_free_before=free_before))
                        if fault:
                            fault("delete_authorized")
                        for row in json_rows(self.result / "materials.jsonl.gz"):
                            path = inside(self.work, self.work / row["path"])
                            if path.exists():
                                path.unlink()
                                if fault:
                                    fault("file_deleted")
                    # No rmtree: unknown late files survive and fail rmdir.
                    for folder in sorted((p for p in self.work.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
                        folder.rmdir()
                    sync_dir(self.work)
                    (self.work / ".owned.json").unlink()
                    if fault:
                        fault("owner_removed")
                    self.work.rmdir()
            elif state != "DELETING":
                raise LifecycleError("Owned source missing before deletion")
            sync_dir(self.work.parent)
            fs = os.statvfs(self.result)
            free_after = fs.f_bavail * fs.f_frsize
            result = dict(identity=self.identity, deleted=True, retained_before_final_report=usage(self.result),
                reclaimed_owned_file_allocated_bytes=receipt["before"]["allocated_bytes"],
                filesystem_free_before=free_before, filesystem_free_after=free_after,
                filesystem_free_delta_shared_volume=None if free_before is None else free_after-free_before,
                pair_audit=pair_receipt, orphan_files=[str(path.relative_to(self.result))for path in self.result.rglob("*.pending")], capabilities=receipt["capabilities"],
                kernel_quota_enforced=False)
            atomic_json(self.result / "finalization.json", result)
            atomic_json(self.result / "state.json", dict(state="DELETED", identity=self.identity))
            return result

def audit_pair(left, right):
    if (left.root != right.root or left.key != right.key or left.plan_sha != right.plan_sha
        or {left.side, right.side} != {"control", "shadow"}):
        raise LifecycleError("Pair identity mismatch")
    sides = {}
    for side in (left, right):
        if side._state()["state"] not in ("SEALED", "DELETED"):
            raise LifecycleError("Both sides must publish evidence")
        receipt = json.loads((side.result / "retention.json").read_bytes())
        verify_retained_artifacts(side.result,receipt)
        single=side.result/'single_side_audit.json'
        if single.exists():
            prior=json.loads(single.read_bytes())
            if prior['sides'][side.side]['retention_sha256']!=sha(side.result/'retention.json'):
                raise LifecycleError('Immutable single-side metadata identity changed')
        if sha(side.result / "trace.jsonl.gz") != receipt["trace"]["sha256"]:
            raise LifecycleError("Pair source changed")
        sides[side.side] = dict(attempt=side.attempt, retention_sha256=sha(side.result / "retention.json"), trace_audit=receipt["trace_audit"])
    comparison = compare_traces(left.result / "trace.jsonl.gz", right.result / "trace.jsonl.gz",
        endpoint_schema=left.plan.get("production_schema")=="release4_endpoint_v1")
    complete=all(item['trace_audit']['status']=='VERIFIED'for item in sides.values())
    terminals={}
    for side in (left,right):
        terminal=next((row for row in json_rows(side.result/'trace.jsonl.gz')if row.get('kind')=='terminal'),{})
        metrics=terminal.get('native_metrics')
        terminals[side.side]=dict(termination_reason=terminal.get('termination_reason'),
            native_success=metrics.get('success')if isinstance(metrics,dict)else None)
    navigation_success=all(value['native_success']==1 for value in terminals.values())
    untruncated=all(value['termination_reason']not in(None,'max_steps')for value in terminals.values())
    result = dict(key=left.key, plan_sha256=left.plan_sha, sides=sides, audit_complete=True,
        business_equivalence=comparison, complete_execution_equivalent=complete and comparison["equal"],
        native_navigation_success=navigation_success,termination=terminals,
        complete_success=complete and comparison["equal"]and navigation_success and untruncated, failure_denominator_preserved=True,
        scope="Audit completed; differences/failures retained, never relabeled success")
    report = left.root / "reports"
    report.mkdir(exist_ok=True)
    immutable_json(report / (left.key+"-"+left.attempt+"-"+right.attempt+"-v3.json"), result)
    return result

def capacity_budget(*, concurrent_workers, activity_peak, rebuild_extra, codec_extra, native_peak,
                    retained_ordinary, fixed_diagnostics, emergency, available):
    values = (concurrent_workers, activity_peak, rebuild_extra, codec_extra, native_peak,
              retained_ordinary, fixed_diagnostics, emergency, available)
    if any(type(v) is not int or v < 0 for v in values) or concurrent_workers == 0:
        raise LifecycleError("Explicit measured byte budgets required")
    active = concurrent_workers * (activity_peak + rebuild_extra + codec_extra + native_peak)
    needed = active + retained_ordinary + fixed_diagnostics + emergency
    return dict(required_bytes=needed, active_bytes=active, available_bytes=available,
        headroom_bytes=available-needed, capacity_admitted=available >= needed,
        kernel_quota_enforced=False, production_ready=False,
        scope="Capacity only; native/global enforcement requires separate acceptance")

def inspect_trace(path):
    """Streaming causal audit, including incomplete attempts in the denominator."""
    pending = None
    calls = steps = resets = 0
    errors = []
    last = None
    for row in json_rows(path):
        kind = row.get("kind")
        if kind == "reset":
            resets += 1
            if last is not None:
                errors.append("noninitial_reset")
        elif kind == "model_input":
            if pending is not None:
                errors.append("unfinished_prior_call")
            pending = row
        elif kind == "model_call":
            if pending is None or row.get("call_id") != pending.get("call_id"):
                errors.append("model_causal_pair")
            elif any(row.get(k) != pending.get(k) for k in FIELDS["model_input"]):
                errors.append("model_input_output_identity")
            pending = None
            calls += 1
        elif kind == "primitive_action":
            steps += 1
        elif kind == "terminal":
            if row.get("steps") != steps or row.get("model_calls") != calls:
                errors.append("terminal_counts")
        last = kind
    if resets != 1:
        errors.append("reset_count")
    if pending is not None:
        errors.append("unfinished_call")
    complete = last == "terminal"
    if not complete:
        errors.append("aborted_or_incomplete")
    return dict(status="VERIFIED" if not errors else "FAILED_OR_INCOMPLETE",
                errors=errors, model_calls=calls, primitive_steps=steps,
                terminal_kind=last, denominator_preserved=True)

class BoundedWriter:
    """Pre-write bound for this codec only, never a native filesystem quota."""
    def __init__(self, stream, limit):
        self.stream, self.limit = stream, limit
    def write(self, data):
        if self.stream.tell() + len(data) > self.limit:
            raise LifecycleError("Codec write would exceed sealed bound")
        return self.stream.write(data)
    def __getattr__(self, name):
        return getattr(self.stream, name)

class EpisodeSession:
    """Kernel-held episode lease plus a nonce/HMAC-bound close acknowledgement.

    A shared model process may stay alive. Only this episode capability is
    revoked. The key remains in the controller result tree, not in public data.
    This proves the registered close protocol, not arbitrary native write quota.
    """
    def __init__(self, episode, role):
        import secrets
        self.episode = episode
        self.role = segment(role)
        if self.role not in episode.entry.get("owner_roles_by_side",{}).get(episode.side,episode.plan["owner_roles"]):
            raise LifecycleError("Unregistered producer role")
        if episode._state()["state"] != "ACTIVE":
            raise LifecycleError("Session starts only on active attempt")
        self.directory = episode.result / "owner_sessions"
        self.directory.mkdir(exist_ok=True)
        self.ticket_path = self.directory / (self.role + ".json")
        self.guard_path = self.directory / (self.role + ".lock")
        if self.ticket_path.exists():
            raise LifecycleError("Producer role already registered")
        self.guard = self.guard_path.open("a+b")
        fcntl.flock(self.guard, fcntl.LOCK_SH)
        self.ticket = dict(identity=episode.identity, role=role,
                           process=process_identity(os.getpid()),
                           nonce=secrets.token_hex(32), key=secrets.token_hex(32))
        atomic_json(self.ticket_path, self.ticket)
        os.chmod(self.ticket_path, 0o600)
        self.closed = False

    def _acknowledge(self, observed):
        import hmac
        if self.closed:
            raise LifecycleError("Session already revoked")
        payload = dict(identity=self.episode.identity, role=self.role,
            process=self.ticket["process"], nonce=self.ticket["nonce"],
            observed=observed, session_revoked=True)
        signature = hmac.new(bytes.fromhex(self.ticket["key"]), canonical(payload), hashlib.sha256).hexdigest()
        self.guard.close()
        self.closed = True
        return dict(payload=payload, signature=signature)

    def close_files(self, handles):
        if self.episode.plan['owner_components'][self.role]!='file_owner':
            raise LifecycleError('File closure cannot acknowledge native/memory owner')
        if not handles:
            raise LifecycleError("Actual episode handles required")
        descriptions = []
        for handle in handles:
            if handle.closed:
                raise LifecycleError("Handle not owned by active session")
            require_component_path(self.episode,self.role,Path(handle.name))
            descriptions.append(str(handle.name))
            handle.close()
        if not all(handle.closed for handle in handles):
            raise LifecycleError("File owner did not close")
        return self._acknowledge(dict(component="file_owner", closed_files=descriptions))

    def close_memory(self, store):
        from .store import EpisodeStore
        if not isinstance(store, EpisodeStore):
            raise LifecycleError("Actual EpisodeStore required")
        require_component_path(self.episode,self.role,store.root)
        store.close()
        observed = store.release_audit()
        if not observed["memory_closed"] or not observed["pins_zero"] or any(observed["cache_entries"].values()):
            raise LifecycleError("Actual memory release failed")
        assert_no_open_files(store.root)
        return self._acknowledge(dict(component="memory", release=observed, root=str(store.root)))

    def close_pose_provider(self,bridge):
        from graphAdapter.observation_pose.pose_bridge import PoseBridge
        from graphAdapter.interfaces.pose import PoseProvider
        if self.episode.plan['owner_components'][self.role]!='pose_provider':raise LifecycleError('Explicit pose-provider owner required')
        if not isinstance(bridge,PoseBridge) or bridge.pose_provider!='simulator_ground_truth' or not isinstance(bridge.adapter,PoseProvider):
            raise LifecycleError('Matching shared pose-provider bridge required')
        adapter=bridge.adapter;identity=adapter.get_mapping_session_identity()
        scope_path=self.episode.result/'production_scope.json'
        if scope_path.exists() and json.loads(scope_path.read_bytes())['scope']['episode_uid']!=identity.episode_id:
            raise LifecycleError('Pose-provider session belongs to another episode')
        bridge.shutdown();bridge.frames.clear()
        audit=adapter.release_audit()
        if (audit.get('source')!='simulator_ground_truth' or audit.get('closed')is not True or audit.get('buffered_frames')!=0
            or any(audit.get(key)is not True for key in ('latest_cleared','origin_cleared','reader_released','episode_cleared'))
            or audit.get('simulator_owned')is not False):
            raise LifecycleError('Pose-provider resources were not released')
        return self._acknowledge(dict(component='pose_provider',episode_id=identity.episode_id,
            episode_instance=identity.episode_instance,release=audit))

    def close_pose(self, bridge):
        from graphAdapter.observation_pose.pose_bridge import PoseBridge
        if not isinstance(bridge, PoseBridge):
            raise LifecycleError("Actual PoseBridge required")
        adapter = bridge.adapter
        from poseAdapter.pose_adapter import PoseAdapter
        if not isinstance(adapter,PoseAdapter):raise LifecycleError('Actual PoseAdapter required')
        native=adapter._native
        proc=getattr(native,'proc',None)
        native_owner=process_identity(proc.pid)if proc is not None else None
        artifacts=adapter.artifact_identity()
        if(ep_result:=self.episode.result/'routes.json').exists():
            for key in('native_session','pose_log'):
                if artifacts.get(key):require_component_path(self.episode,self.role,Path(artifacts[key]))
        bridge.shutdown()
        if native_owner is not None:assert_owners_closed([native_owner])
        bridge.frames.clear()
        if not adapter._closed or adapter.episode_id is not None or adapter._native is not None or adapter._original is not None:
            raise LifecycleError("Native adapter did not close")
        if adapter._owned_log is not None or adapter._observation_cache is not None:
            raise LifecycleError('Native episode cache/log still owned')
        return self._acknowledge(dict(component="pose", adapter_closed=True,
                                     exited_native_owner=native_owner,artifact_identity=artifacts))

    def bind_remote_memory(self,root,episode_uid):
        root=Path(root).absolute()
        allowed=Path(__file__).resolve().parents[4]/'outputs/graph_memory'
        if root.resolve()!=root or allowed not in root.parents or 'evaluation_private'in root.parts:
            raise LifecycleError('Remote memory scope outside approved outputs')
        if self.role!='memory' or self.episode.plan['owner_components'][self.role]!='memory':
            raise LifecycleError('Only memory sessions can bind a private memory ticket')
        self.ticket.update(expected_store_root=str(root),expected_episode_uid=episode_uid)
        atomic_json(self.ticket_path,self.ticket)
        os.chmod(self.ticket_path,0o600)
        return self.ticket

    def accept_remote_acknowledgement(self,acknowledgement):
        if self.closed:raise LifecycleError('Session already revoked')
        verify_close_acknowledgement(self.ticket,acknowledgement,'memory')
        self.guard.close();self.closed=True
        atomic_json(self.directory/(self.role+'-close.json'),acknowledgement)
        return acknowledgement

    def close_trace(self, recorder):
        from case1_runtime.trace import TraceRecorder
        if not isinstance(recorder,TraceRecorder):raise LifecycleError('Actual TraceRecorder required')
        require_component_path(self.episode,self.role,recorder.directory)
        recorder.close()
        if recorder.handle is not None or recorder.pending_call is not None:
            raise LifecycleError('Host episode trace remains active')
        assert_no_open_files(recorder.directory)
        result=json.loads((recorder.directory/'result.json').read_bytes())
        trace=recorder.directory/'trace.jsonl'
        if sha(trace)!=result['trace_sha256']:raise LifecycleError('Host terminal identity mismatch')
        return self._acknowledge(dict(component='host_trace',trace_sha256=sha(trace),
            task_key=result['task_key'],termination_reason=result['termination_reason'],
            primitive_steps=result['primitive_steps'],model_calls=result['model_calls']))

def verify_session_receipts(episode, receipts):
    import hmac
    if not isinstance(receipts, dict) or set(receipts) != set(episode.entry.get("owner_roles_by_side",{}).get(episode.side,episode.plan["owner_roles"])):
        raise LifecycleError("Every registered episode owner must acknowledge closure")
    for role, acknowledgement in receipts.items():
        path = episode.result / "owner_sessions" / (segment(role) + ".json")
        ticket = json.loads(path.read_bytes())
        payload = acknowledgement.get("payload", {})
        verify_close_acknowledgement(ticket,acknowledgement,episode.plan['owner_components'][role])
        if payload.get('observed',{}).get('component')!=episode.plan['owner_components'][role]:
            raise LifecycleError('Owner close component mismatch')
        if (ticket["identity"] != episode.identity or payload.get("identity") != episode.identity
            or payload.get("role") != role or payload.get("nonce") != ticket["nonce"]
            or payload.get("process") != ticket["process"] or payload.get("session_revoked") is not True):
            raise LifecycleError("Session close identity/nonce mismatch")
        expected = hmac.new(bytes.fromhex(ticket["key"]), canonical(payload), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, acknowledgement.get("signature", "")):
            raise LifecycleError("Forged session close acknowledgement")
        with exclusive(episode.result / "owner_sessions" / (role + ".lock")):
            pass
    return dict(roles=sorted(receipts), session_capabilities_revoked=True,
                shared_process_exit_required=False)

def audit_single(episode):
    """Publish sufficient immutable evidence to pair after ordinary work is freed."""
    if episode._state()["state"] not in ("SEALED", "DELETING", "DELETED"):
        raise LifecycleError("Single-side evidence not sealed")
    receipt = json.loads((episode.result / "retention.json").read_bytes())
    verify_retained_artifacts(episode.result,receipt)
    for name, description in [("trace.jsonl.gz", receipt["trace"]),
                              ("materials.jsonl.gz", receipt["materials"])]:
        if sha(episode.result / name) != description["sha256"]:
            raise LifecycleError("Single-side evidence corrupted")
    for name, description in receipt.get("evidence_streams", {}).items():
        if sha(episode.result / (name + ".jsonl.gz")) != description["sha256"]:
            raise LifecycleError("Single-side per-frame evidence corrupted")
    result = dict(key=episode.key, plan_sha256=episode.plan_sha, audit_complete=True,
        sides={episode.side:dict(attempt=episode.attempt,
            retention_sha256=sha(episode.result / "retention.json"),
            trace_audit=receipt["trace_audit"])},
        pairing_status="SINGLE_SIDE_VERIFIED_PENDING_PAIR",
        complete_success=False, denominator_preserved=True)
    immutable_json(episode.result / "single_side_audit.json", result)
    return result

def verify_close_acknowledgement(ticket, acknowledgement, component):
    import hmac
    payload=acknowledgement.get("payload",{})
    if (payload.get("identity")!=ticket["identity"] or payload.get("role")!=ticket["role"]
        or payload.get("nonce")!=ticket["nonce"] or payload.get("process")!=ticket["process"]
        or payload.get("session_revoked")is not True
        or payload.get("observed",{}).get("component")!=component):
        raise LifecycleError("Session close identity/component mismatch")
    expected=hmac.new(bytes.fromhex(ticket["key"]),canonical(payload),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,acknowledgement.get("signature","")):
        raise LifecycleError("Forged session close acknowledgement")
    if "expected_store_root"in ticket:
        observed=payload["observed"]
        if observed.get("root")!=ticket["expected_store_root"]or observed.get("episode_uid")!=ticket["expected_episode_uid"]:
            raise LifecycleError("Remote store scope mismatch")
    return payload

def close_remote_memory_session(ticket, store):
    """Runs inside the real private worker; no controller filesystem is mounted."""
    from .store import EpisodeStore
    import hmac
    if not isinstance(store,EpisodeStore)or ticket.get("role")!="memory":
        raise LifecycleError("Typed memory owner ticket required")
    if str(store.root)!=ticket.get("expected_store_root")or store.episode_uid!=ticket.get("expected_episode_uid"):
        raise LifecycleError("Ticket belongs to another memory episode")
    store.close()
    release=store.release_audit()
    if not release["memory_closed"]or not release["pins_zero"]or any(release["cache_entries"].values()):
        raise LifecycleError("Remote memory release failed")
    assert_no_open_files(store.root)
    payload=dict(identity=ticket["identity"],role=ticket["role"],process=ticket["process"],
        nonce=ticket["nonce"],session_revoked=True,
        observed=dict(component="memory",root=str(store.root),episode_uid=store.episode_uid,
            namespace_owner=process_identity(os.getpid()),release=release,
            scope="private worker episode closed;fixed models/process may remain"))
    signature=hmac.new(bytes.fromhex(ticket["key"]),canonical(payload),hashlib.sha256).hexdigest()
    return dict(payload=payload,signature=signature)

def verify_retained_artifacts(result_root, receipt):
    """All declared capability bytes must survive, including previews/metadata."""
    root=Path(result_root)
    artifacts=receipt.get("retained_artifacts")
    if artifacts is None:
        # Explicit v1 compatibility for earlier package/ordinary receipts.
        artifacts={"trace.jsonl.gz":receipt["trace"],"materials.jsonl.gz":receipt["materials"]}
        artifacts.update({name+".jsonl.gz":value for name,value in receipt.get("evidence_streams",{}).items()})
        package=receipt.get("qualification",{}).get("package")
        if package:artifacts["memory.tar.gz"]=package
        if not package and receipt.get("capabilities"):
            raise LifecycleError("Legacy standalone capability has no artifact identity")
    for name, description in artifacts.items():
        path=inside(root,root/name)
        if not path.is_file()or sha(path)!=description["sha256"]:
            raise LifecycleError("Retained capability artifact corrupted:"+name)
    return True

def immutable_json(path, value):
    path=Path(path)
    if path.exists():
        if canonical(json.loads(path.read_bytes()))!=canonical(value):
            raise LifecycleError("Immutable audit receipt changed")
        return
    atomic_json(path,value)

def verify_audit_full_inputs(root, memory_root, *, expected_source_sha256):
    """Qualify actual serialized inputs, not names or saved=true."""
    from .store import load_episode
    from graphAdapter.evaluation.recordings import CommittedRecording,APPROVED000
    from graphAdapter.observation_packet import ObservationPacket,thaw
    import numpy as np
    import sqlite3
    root=Path(root)
    refs=json.loads((root/"audit_inputs.json").read_bytes())
    required={"host_trace","source_packets","flow_trace","source_locator_map","calibration",
              "native_db","source_lock","source_archive","effective_config"}
    if set(refs)!=required:raise LifecycleError("Complete audit input roles required")
    paths={}
    for name,ref in refs.items():
        path=inside(root,root/ref["path"])
        if sha(path)!=ref["sha256"]:raise LifecycleError("Audit input identity mismatch")
        paths[name]=path
    lock=json.loads(paths["source_lock"].read_bytes())
    files=lock.get("files")
    if (not expected_source_sha256 or not isinstance(files,list)or not files
        or lock.get("source_sha256")!=expected_source_sha256
        or hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()!=expected_source_sha256):
        raise LifecycleError("Audit source lock not bound to presealed source")
    project=Path(__file__).resolve().parents[4]
    expected={str(Path(row["path"]).relative_to(project)):row["sha256"]for row in files}
    seen=set()
    with tarfile.open(paths["source_archive"],"r|gz")as tar:
        for member in tar:
            if not member.isfile()or member.name not in expected or member.name in seen:
                raise LifecycleError("Unexpected source archive member")
            h=hashlib.sha256()
            data=tar.extractfile(member)
            for block in iter(lambda:data.read(1024**2),b""):h.update(block)
            if h.hexdigest()!=expected[member.name]:raise LifecycleError("Archived source differs from source lock")
            seen.add(member.name)
    if seen!=set(expected):raise LifecycleError("Source archive incomplete")
    config=json.loads(paths["effective_config"].read_bytes())
    if config.get("feature")!="map_memory"or config.get("map_memory",{}).get("enabled")is not True:
        raise LifecycleError("Audit effective model/map configuration missing")
    trace_audit=inspect_trace(paths["host_trace"])
    if trace_audit["status"]!="VERIFIED":raise LifecycleError("Full audit host trace is incomplete")
    verify_host_images(paths["host_trace"],root)
    with paths["host_trace"].open()as stream:reset=json.loads(stream.readline())
    db_path=paths["native_db"]
    if Path(str(db_path)+"-wal").exists()and Path(str(db_path)+"-wal").stat().st_size:
        raise LifecycleError("Native audit database must be closed/checkpointed")
    db=sqlite3.connect("file:"+str(db_path)+"?mode=ro&immutable=1",uri=True)
    try:
        if db.execute("PRAGMA quick_check").fetchone()[0]!="ok":raise LifecycleError("Native database integrity")
        tables={row[0]for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"Node","Data"}<=tables:raise LifecycleError("Native RTAB source tables missing")
        native_nodes=db.execute("SELECT COUNT(*) FROM Node").fetchone()[0]
        if native_nodes<1:raise LifecycleError("Native audit contains no recorded keyframe")
    finally:db.close()
    locator=json.loads(paths["source_locator_map"].read_bytes())
    raw={};aligned={};committed={}
    for event in json_rows(paths["flow_trace"]):
        if event.get("kind")=="raw_archive":raw[event["frame_uid"]]=event
        elif event.get("kind")=="alignment":aligned[event["frame_uid"]]=event
        elif event.get("kind")=="observation_packet":committed[event["frame_uid"]]=event["packet"]
    recording=CommittedRecording.__new__(CommittedRecording)
    recording.root=paths["calibration"].parent.parent;recording._bridges={}
    recording.legacy_alignment_storage=expected_source_sha256 in {
        APPROVED000,"f137ea88e19336ea3822aeeb9da85c6f5227cbdbe223fd77df88bce99f6ffbc3"}
    reader=load_episode(memory_root,cache_bytes=0)
    seen_frames=set();input_hashes=[]
    try:
        episode=reader.identity["episode_uid"]
        for record in json_rows(paths["source_packets"]):
            packet=ObservationPacket(**record);uid=packet.frame_uid
            if uid in seen_frames or packet.episode_uid!=episode or uid not in reader._graph["views"]:
                raise LifecycleError("Audit packet membership")
            if committed.get(uid)!=record:raise LifecycleError("Audit flow/packet commit differs")
            capture=thaw(reader.get_view(uid,include_images=False)["capture"])
            if any(capture.get(k)!=v for k,v in record.items()):raise LifecycleError("Audit map/source packet differs")
            if packet.to_record()["identity"]["member"]!=reset["episode_scope"]["member"]:
                raise LifecycleError("Host/source member mismatch")
            moved=dict(record)
            for key in ("raw_rgb_ref","raw_depth_ref","aligned_ref"):
                ref=record[key]
                if ref is not None:
                    entry=locator.get(ref)
                    if not isinstance(entry,dict)or entry.get("codec")!="npy":raise LifecycleError("Explicit lossless source locator missing")
                    moved[key]=str(inside(root,root/entry["path"]))
            material=recording.materialize(ObservationPacket(**moved),raw[uid],aligned.get(uid))
            archived=reader.get_view(uid,include_images=True,include_depth=True)
            from graphAdapter.observation_pose.alignment import array_hash
            if array_hash(material["rgb"])!=array_hash(archived["raw_rgb"]):
                raise LifecycleError("Audit RGB differs from consumed image")
            for name in ("raw_depth","aligned_depth","valid_mask"):
                if material[name]is not None and array_hash(material[name])!=array_hash(archived["depth"][name]):
                    raise LifecycleError("Audit exact fusion source differs")
            input_hashes.append([uid,array_hash(material["rgb"]),None if material["raw_depth"]is None else array_hash(material["raw_depth"])])
            seen_frames.add(uid)
        if seen_frames!=set(reader._graph["views"]):raise LifecycleError("Full audit frame coverage")
    finally:reader.close()
    return dict(frames=len(seen_frames),all_serialized_inputs_read=True,
        source_sha256=expected_source_sha256,source_archive_files=len(seen),
        native_database_integrity="ok",native_keyframes=native_nodes,
        input_digest=hashlib.sha256(canonical(input_hashes)).hexdigest(),trace_audit=trace_audit,
        scope="Complete serialized input/nativeDB audit;weights/runtime remain shared fixed resources")

def export_graph_metadata(memory_root, target):
    """Readable nodes/edges/coordinates without claiming retained image sources."""
    from .store import load_episode
    reader=load_episode(memory_root,cache_bytes=0)
    try:
        reader.verify(hashes=True,references=True)
        graph=reader._graph
        value=dict(revision=reader.snapshot_id,episode_uid=reader.identity["episode_uid"],
            versions=dict(reader.versions),cutoff=dict(reader.cutoff),
            nodes=dict(views=graph["views"],entities=graph.get("entities",[])),
            edges=graph.get("edges",[]),aliases=graph.get("aliases",[]),
            source_capabilities=dict(queryable=False,rebuildable=False))
        atomic_json(target,value)
        return value
    finally:reader.close()


def require_component_path(episode,role,path):
    path=Path(path).absolute()
    if path==episode.work or episode.work in path.parents:
        return inside(episode.work,path)
    registry=episode.result/'routes.json'
    if registry.exists():
        from .routing import RunRouting
        routes=json.loads(registry.read_bytes())
        if routes['identity']!=episode.identity:raise LifecycleError('Component routing identity')
        for row in routes['scopes']:
            base=Path(row['path'])if row['state']!='GATHERED'else episode.work/row['target']
            if row['role']==role and(base==path or base in path.parents):
                inside(base,path)
                marker=json.loads((base/'.producer-owner.json').read_bytes())
                if marker!=dict(identity=episode.identity,role=role,nonce=row['nonce']):
                    raise LifecycleError('Component creation marker changed')
                if(base.stat().st_dev,base.stat().st_ino)!=(row['device'],row['inode']):
                    raise LifecycleError('Component creation inode changed')
                return path
    raise LifecycleError('Component is not owned by this new episode')
