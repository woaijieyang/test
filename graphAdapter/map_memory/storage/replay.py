"""Own temporary tile material during one full pose-correction replay."""
import json
import os
import re
import shutil
import uuid

import numpy as np

from . import archive

_NAME = re.compile(r"tile-replay-[a-f0-9]{32}")
_MARKER = "owner.json"


def _pending(store):
    pending = store.root / ".pending"
    if pending.resolve() != pending or not pending.is_relative_to(store.root):
        raise archive.IntegrityError("Replay workspace escapes the episode")
    return pending


def _owner(store):
    return {"kind": "graph001_tile_replay_v1", "episode_uid": store.episode_uid,
            "episode_root": str(store.root)}


def _discard(store, path):
    if path.parent != _pending(store) or path.resolve() != path or not _NAME.fullmatch(path.name):
        raise archive.IntegrityError("Replay scratch is not owned by this episode")
    marker = path / _MARKER
    if marker.is_symlink() or json.loads(marker.read_bytes()) != _owner(store):
        raise archive.IntegrityError("Replay scratch owner mismatch")
    shutil.rmtree(path)


def recover_replay_scratch(store):
    """Call after acquiring the episode writer lock, before accounting bytes."""
    pending = _pending(store)
    for path in pending.glob("tile-replay-*"):
        if not _NAME.fullmatch(path.name) or not path.is_dir() or path.is_symlink():
            raise archive.IntegrityError("Unexpected replay scratch entry")
        if not any(path.iterdir()):
            # A process may exit after mkdir, before publishing its marker.
            path.rmdir()
        else:
            marker = path / _MARKER
            marker_tmp = path / ".pending"
            if not marker.exists() and not marker.is_symlink() and list(path.iterdir()) == [marker_tmp]:
                # Immutable marker publication can be interrupted before its link.
                if marker_tmp.resolve() != marker_tmp or not marker_tmp.is_dir():
                    raise archive.IntegrityError("Unexpected replay marker scratch")
                entries = list(marker_tmp.iterdir())
                expected = archive.canonical(_owner(store))
                if len(entries) <= 1 and all(
                        x.is_file() and not x.is_symlink()
                        and re.fullmatch(r"[a-f0-9]{32}\.tmp", x.name)
                        and expected.startswith(x.read_bytes()) for x in entries):
                    for x in entries:
                        x.unlink()
                    marker_tmp.rmdir()
                    path.rmdir()
                    continue
                raise archive.IntegrityError("Unexpected unpublished replay owner marker")
            _discard(store, path)


class ReplayTileBacking:
    """Reuse the archive tile codec without publishing intermediate blobs."""

    def __init__(self, store, *, minimum_free_bytes=0):
        self.store = store
        self.minimum_free_bytes = minimum_free_bytes
        self.root = _pending(store) / ("tile-replay-" + uuid.uuid4().hex)
        self._files = {}
        self._logical = 0
        self._allocated = 0
        self.metrics = {
            "staged_unique_writes": 0, "staged_logical_bytes_written": 0,
            "peak_staged_logical_bytes": 0, "peak_staged_allocated_bytes": 0,
            "final_unique_blobs": 0, "new_durable_blob_bytes": 0,
            "minimum_filesystem_free_bytes_observed": None,
        }

    def __enter__(self):
        self.root.mkdir(parents=True, exist_ok=False)
        archive._write_immutable(self.root, _MARKER, archive.canonical(_owner(self.store)))
        return self

    def __exit__(self, *exc):
        _discard(self.store, self.root)

    def _check_free(self, required_bytes=0):
        from ..geometry.core import CapacityError
        fs = os.statvfs(self.root)
        free = fs.f_bavail * fs.f_frsize
        prev = self.metrics["minimum_filesystem_free_bytes_observed"]
        self.metrics["minimum_filesystem_free_bytes_observed"] = free if prev is None else min(free, prev)
        required_allocation = ((required_bytes + fs.f_frsize - 1) // fs.f_frsize) * fs.f_frsize
        if free < self.minimum_free_bytes + required_allocation:
            raise CapacityError("Filesystem reserve exhausted during tile replay;source/history preserved")

    def put_arrays(self, arrays):
        data = archive.encode_arrays(arrays)
        rel = "blobs/" + archive.digest(data) + ".npz"
        path = archive._owned(self.root, rel)
        # The immutable writer returns an existing content hash without a temporary write.
        self._check_free(0 if path.is_file() else len(data))
        stored = archive._write_immutable(self.root, rel, data, stage="staged_tile_blob")
        ref = dict(stored, arrays={key: archive.array_descriptor(np.asarray(value))
                                   for key, value in arrays.items()})
        if rel not in self._files:
            st = (self.root / rel).stat()
            allocated = st.st_blocks * 512
            self._files[rel] = (st.st_size, allocated)
            self._logical += st.st_size
            self._allocated += allocated
            self.metrics["staged_unique_writes"] += 1
            self.metrics["staged_logical_bytes_written"] += st.st_size
            self.metrics["peak_staged_logical_bytes"] = max(
                self.metrics["peak_staged_logical_bytes"], self._logical)
            self.metrics["peak_staged_allocated_bytes"] = max(
                self.metrics["peak_staged_allocated_bytes"], self._allocated)
        return ref

    get_arrays = archive.RawArchive.get_arrays
    save_tile = archive.RawArchive.save_tile
    load_tile = archive.RawArchive.load_tile

    def prune(self, records):
        """Discard only superseded staged files after the manager installs its new records."""
        current = {record["blob"]["path"] for record in records}
        for rel in self._files.keys() - current:
            path = archive._owned(self.root, rel)
            if path.is_symlink():
                raise archive.IntegrityError("Replay blob became a symlink")
            path.unlink()
            logical, allocated = self._files.pop(rel)
            self._logical -= logical
            self._allocated -= allocated

    def promote(self, records):
        """Commit only final content-addressed files into the durable episode namespace."""
        final = {record["blob"]["path"]: record["blob"] for record in records}
        self.metrics["final_unique_blobs"] = len(final)
        for rel, ref in final.items():
            if rel not in self._files:
                raise archive.IntegrityError("Final replay tile lacks staged ownership")
            required = 0 if (self.store.root / rel).is_file() else ref["bytes"]
            self._check_free(required)
            self.metrics["new_durable_blob_bytes"] += self.store.import_replay_blob(self.root, ref)
        return dict(self.metrics)


class WriteBackReplayTileBacking(ReplayTileBacking):
    """Bounded write-back, admitted after the source frame transaction commits.

    save_tile holds a reference to the source manager's existing write-set tile;
    it does not copy its arrays. prune drops superseded versions and admits the
    live write set into the byte-bounded cache. This avoids encoding old versions
    just to admit replacements that the same source frame already owns.
    """
    def __init__(self, store, *, minimum_free_bytes=0, max_buffer_bytes=64*1024*1024,
                 max_pending_tiles=64):
        super().__init__(store,minimum_free_bytes=minimum_free_bytes)
        from collections import OrderedDict
        if type(max_buffer_bytes) is not int or max_buffer_bytes<0:
            raise ValueError("Nonnegative replay buffer byte budget required")
        if type(max_pending_tiles) is not int or max_pending_tiles<1:
            raise ValueError("Positive pending tile count bound required")
        self.max_buffer_bytes=max_buffer_bytes;self.max_pending_tiles=max_pending_tiles
        self._buffer=OrderedDict();self._buffer_bytes=0;self._sequence=0
        self._pending=OrderedDict();self._pending_bytes=0
        self.metrics.update(writeback_save_requests=0,writeback_cache_loads=0,
            writeback_superseded_drops=0,writeback_flushes=0,writeback_evictions=0,
            writeback_peak_array_bytes=0,writeback_buffer_array_bytes=0,
            writeback_pending_peak_array_bytes=0,writeback_pending_array_bytes=0,
            writeback_pending_peak_tiles=0)

    def __exit__(self,*exc):
        try:return super().__exit__(*exc)
        finally:
            self._buffer.clear();self._buffer_bytes=0
            self._pending.clear();self._pending_bytes=0
            self.metrics["writeback_buffer_array_bytes"]=0
            self.metrics["writeback_pending_array_bytes"]=0

    def _drop(self,token):
        if token in self._pending:
            tile,record,size=self._pending.pop(token);self._pending_bytes-=size
            self.metrics["writeback_pending_array_bytes"]=self._pending_bytes
        else:
            tile,record,size=self._buffer.pop(token);self._buffer_bytes-=size
            self.metrics["writeback_buffer_array_bytes"]=self._buffer_bytes
        return tile,record,size

    def _flush(self,token):
        tile,record,size=self._buffer[token]
        durable=super().save_tile(tile)
        record.clear();record.update(durable)
        self._drop(token);self.metrics["writeback_flushes"]+=1

    def save_tile(self,tile):
        self.metrics["writeback_save_requests"]+=1
        meta,arrays=tile.export();size=sum(a.nbytes for a in arrays.values())
        if not self.max_buffer_bytes or size>self.max_buffer_bytes:
            return super().save_tile(tile)
        if len(self._pending)>=self.max_pending_tiles:
            from ..geometry.core import CapacityError
            raise CapacityError("Replay write set exceeds one source frame's candidate bound")
        token=str(self._sequence);self._sequence+=1
        record=dict(meta=meta,_pending_tile=token)
        self._pending[token]=(tile,record,size);self._pending_bytes+=size
        self.metrics["writeback_pending_array_bytes"]=self._pending_bytes
        self.metrics["writeback_pending_peak_array_bytes"]=max(
            self.metrics["writeback_pending_peak_array_bytes"],self._pending_bytes)
        self.metrics["writeback_pending_peak_tiles"]=max(
            self.metrics["writeback_pending_peak_tiles"],len(self._pending))
        return record

    def load_tile(self,record):
        token=record.get("_pending_tile")
        if token is None:return super().load_tile(record)
        entry=self._pending.get(token) or self._buffer.get(token)
        if entry is None or entry[1] is not record:
            raise archive.IntegrityError("Pending tile is not owned by this replay")
        tile=entry[0]
        if token in self._buffer:self._buffer.move_to_end(token)
        self.metrics["writeback_cache_loads"]+=1
        # The original core-only disk codec resets halos on eviction reload.
        from ..geometry.core import TSDFTile
        meta,arrays=tile.export();meta["blob_layout"]="owner_core_only"
        h=meta["halo_cells"];core=tuple(slice(h,h+int(n)) for n in meta["core_cells"])
        expanded={}
        for name,a in arrays.items():
            expanded[name]=np.full(a.shape,-1 if name=="tsdf" else 0,dtype=a.dtype)
            expanded[name][core]=a[core]
        return TSDFTile.restore(meta,expanded)

    def prune(self,records):
        records=list(records)
        live={r["_pending_tile"] for r in records if "_pending_tile" in r}
        # Source manager has installed all frame changes; unreferenced prior
        # versions can now be released without encoding or corrupting rollback.
        for token in list(self._buffer)+list(self._pending):
            if token not in live:
                self._drop(token);self.metrics["writeback_superseded_drops"]+=1
        for token in list(self._pending):
            entry=self._pending[token];size=entry[2]
            while self._buffer and self._buffer_bytes+size>self.max_buffer_bytes:
                self._flush(next(iter(self._buffer)))
                self.metrics["writeback_evictions"]+=1
            self._drop(token);self._buffer[token]=entry;self._buffer_bytes+=size
            self.metrics["writeback_buffer_array_bytes"]=self._buffer_bytes
            self.metrics["writeback_peak_array_bytes"]=max(
                self.metrics["writeback_peak_array_bytes"],self._buffer_bytes)
        super().prune(r for r in records if "_pending_tile" not in r)

    def promote(self,records):
        records=list(records);self.prune(records)
        for record in records:
            token=record.get("_pending_tile")
            if token is not None:
                entry=self._buffer.get(token)
                if entry is None or entry[1] is not record:
                    raise archive.IntegrityError("Cannot publish a foreign pending tile")
                self._flush(token)
        if self._buffer or self._pending or any("_pending_tile" in r for r in records):
            raise archive.IntegrityError("Unresolved pending tile before publication")
        return super().promote(records)
