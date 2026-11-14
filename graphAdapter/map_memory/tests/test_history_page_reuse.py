"""Cold history audit must reuse verified raw pages without weakening validation."""
import collections
from contextlib import closing
import sqlite3
import zlib
import pytest
from graphAdapter.map_memory.storage import pages, store
from test_storage import EP, archive, publish, capture


def recording(tmp_path, count=8):
    writer = store.EpisodeStore(tmp_path / 'map', EP, dataset='r2r')
    identities = []
    try:
        for seq in range(1, count + 1):
            archive(writer, seq)
            identities.append(publish(writer, list(range(1, seq + 1)), version=seq)['snapshot_id'])
    finally:
        writer.close()
    return tmp_path / 'map', identities


def test_history_verifies_each_unchanged_page_once_and_keeps_each_version(tmp_path, monkeypatch):
    root, identities = recording(tmp_path)
    counter = collections.Counter()
    original = pages.decode_page
    def counted(key, row):
        counter[key] += 1
        return original(key, row)
    monkeypatch.setattr(pages, 'decode_page', counted)
    monkeypatch.setattr(store, 'decode_page', counted)
    reader = store.load_episode(root)
    try:
        counter.clear()
        history = list(reader.iter_verified_history())
        assert [row['snapshot_id'] for row in history] == list(reversed(identities))
        for row in history:
            version = row['versions']['pose_map_version']
            assert version == row['cutoff']['capture_seq']
            assert all(view['pose_map_version'] == version for view in row['graph']['views'].values())
        # This fails in the old implementation: every ancestor discards its cache.
        assert sum(counter.values()) == len(counter), dict(counter)
    finally:
        reader.close()


def test_fresh_history_audit_cannot_reuse_pages_verified_before_corruption(tmp_path):
    root, identities = recording(tmp_path, 4)
    reader = store.load_episode(root)
    try:
        assert len(list(reader.iter_verified_history())) == 4
        with sqlite3.connect(root / 'pages.sqlite3') as db:
            key = db.execute('SELECT root FROM revisions WHERE id=?', (identities[0],)).fetchone()[0]
            db.execute('UPDATE nodes SET data=? WHERE id=?', (b'corrupted', key))
        with pytest.raises((store.IntegrityError, zlib.error)):
            list(reader.iter_verified_history())
    finally:
        reader.close()


def test_tiny_reader_cache_changes_no_history_content(tmp_path):
    root, _ = recording(tmp_path, 4)
    baseline = store.load_episode(root)
    tiny = store.load_episode(root, cache_bytes=128)
    try:
        def content(reader):
            return [(row['snapshot_id'], store.canonical(row['graph'])) for row in reader.iter_verified_history()]
        assert content(tiny) == content(baseline)
        assert tiny.last_history_audit['peak_cache_bytes'] <= tiny.last_history_audit['cache_limit_bytes'] == 64
    finally:
        tiny.close(); baseline.close()


def test_forced_check_bypasses_cached_page_and_detects_corruption(tmp_path):
    root, _ = recording(tmp_path, 2)
    cache = pages.HistoryPageCache(root, 1024 * 1024)
    reader = store.SnapshotReader(root, _history_cache=cache)
    try:
        key = reader.pages.root_node
        reader.pages.node(key)
        with sqlite3.connect(root / 'pages.sqlite3') as db:
            db.execute('UPDATE nodes SET data=? WHERE id=?', (b'corrupted', key))
        with pytest.raises((store.IntegrityError, zlib.error)):
            reader.pages.node(key, force=True)
        assert key not in cache.items
    finally:
        reader.close(); cache.clear()


def test_cache_cannot_cross_episode_root_and_early_close_releases_audit(tmp_path):
    first, _ = recording(tmp_path / 'first', 2)
    second, _ = recording(tmp_path / 'second', 2)
    cache = pages.HistoryPageCache(first, 1024 * 1024)
    with pytest.raises(store.IntegrityError, match='another map root'):
        store.SnapshotReader(second, _history_cache=cache)
    reader = store.load_episode(first)
    iterator = reader.iter_verified_history()
    try:
        next(iterator); iterator.close()
        assert reader.last_history_audit['complete'] is False
    finally:
        iterator.close(); reader.close(); cache.clear()


def test_history_reuses_unchanged_files_already_verified_by_same_reader(tmp_path):
    root, _ = recording(tmp_path, 4)
    reader = store.load_episode(root)
    try:
        reader.verify(hashes=True, references=True)
        before = reader.verifier.bytes_read
        assert len(list(reader.iter_verified_history())) == 4
        # Current contains all source files in this append-only fixture.
        assert reader.verifier.bytes_read == before
    finally:
        reader.close()


def test_cached_file_receipt_detects_same_size_corruption_even_if_mtime_restored(tmp_path):
    import os
    root, _ = recording(tmp_path, 4)
    reader = store.load_episode(root)
    try:
        reader.verify(hashes=True, references=True)
        path = next((root / 'observations').glob('*.rgb.png'))
        before = path.stat(); data = path.read_bytes()
        path.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        with pytest.raises(store.IntegrityError, match='checksum'):
            list(reader.iter_verified_history())
    finally:
        reader.close()


@pytest.mark.parametrize('fault',['data','children','deleted'])
def test_online_cache_rejects_stale_sql_rows_on_new_pins(tmp_path,fault):
    root,sids=recording(tmp_path,3)
    cache=pages.HistoryPageCache(root,2**20,episode=EP)
    one=store.load_episode(root,revision=sids[-1],_history_cache=cache)
    key=one.pages.root_node
    try:one.pages.node(key)
    finally:one.close()
    try:
        with sqlite3.connect(root/'pages.sqlite3') as db:
            if fault=='data':db.execute('UPDATE nodes SET data=? WHERE id=?',(b'corrupt',key))
            if fault=='children':db.execute('UPDATE nodes SET children=? WHERE id=?',('["wrong"]',key))
            if fault=='deleted':db.execute('DELETE FROM nodes WHERE id=?',(key,))
        with pytest.raises(store.IntegrityError):
            with closing(store.load_episode(root,revision=sids[-1],_history_cache=cache)) as later:
                later.pages.node(key)
        assert key not in cache.items
    finally:cache.close()
    with pytest.raises(store.IntegrityError):cache.bind(root,EP)


def test_online_shared_pages_resolve_each_context_and_do_not_keep_a_read_lock(tmp_path):
    root,sids=recording(tmp_path,4)
    cache=pages.HistoryPageCache(root,2**20,episode=EP)
    for sid in [sids[2],sids[0],sids[3],sids[1],sids[2]]:
        with closing(store.load_episode(root,revision=sid)) as cold:
            expected=cold._graph
        with closing(store.load_episode(root,revision=sid,_history_cache=cache)) as warm:
            assert warm._graph==expected and warm.snapshot_id==sid
    assert cache.hits>0 and cache.bytes<=cache.limit
    import fcntl
    with (root/'pins.lock').open('rb') as f:
        fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
    with pytest.raises(store.IntegrityError):cache.bind(root,'wrong')
    cache.close()
    assert cache.bytes==0 and not cache.items
