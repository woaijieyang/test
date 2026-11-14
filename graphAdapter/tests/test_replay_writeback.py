import copy
import numpy as np
import pytest
from graphAdapter.map_memory.storage.store import EpisodeStore,IntegrityError
from graphAdapter.map_memory.storage.replay import ReplayTileBacking,WriteBackReplayTileBacking
from graphAdapter.map_memory.geometry.core import TSDFSubmapManager,TSDFTile,S


def run(root,cls,budget=None,resident=2):
    store=EpisodeStore(root,'ep-writeback',dataset='r2r')
    options={} if budget is None else dict(max_buffer_bytes=budget)
    with cls(store,**options) as backing:
        manager=TSDFSubmapManager([0,0,0],voxel_size=.25,core_size=(2.,2.,2.),
            max_resident_tiles=resident,backing=backing)
        rgb=np.zeros((8,8,3),np.uint8);depth=np.full((8,8),2.13,np.float32);mask=np.ones((8,8),bool)
        k=np.array([[3.75,0,3.125],[0,3.75,3.375],[0,0,1.]])
        results=[]
        for i in range(8):
            pose=S.copy();pose[:3,3]=[(i%3)*.3-.5,0,-.5]
            results.append(manager.integrate('e:f'+str(i),rgb,depth,mask,k,pose,source_hash=str(i)))
            backing.prune(manager.records.values())
            if isinstance(backing,WriteBackReplayTileBacking):
                assert backing._buffer_bytes<=backing.max_buffer_bytes
        metrics=backing.promote(manager.records.values())
        assert all('blob' in r and '_pending_tile' not in r for r in manager.records.values())
        manager.backing=store
        state=manager.export()
        arrays={key:{n:a.copy() for n,a in store.load_tile(record).arrays().items()}
                for key,record in manager.records.items()}
    assert not list((store.root/'.pending').glob('tile-replay-*'))
    store.close()
    return state,arrays,results,metrics


@pytest.mark.parametrize('budget,resident',[(0,1),(1,1),(20000,1),(1024*1024,1),(1024*1024,16)])
def test_writeback_matches_source_codec_and_all_final_arrays(tmp_path,budget,resident):
    a=run(tmp_path/'original',ReplayTileBacking,resident=resident)
    b=run(tmp_path/'candidate',WriteBackReplayTileBacking,budget,resident)
    assert a[0]==b[0] and a[2]==b[2]
    for key in a[1]:
        for name in a[1][key]:np.testing.assert_array_equal(a[1][key][name],b[1][key][name])
    if budget>=1024*1024:
        assert b[3]['staged_unique_writes']<a[3]['staged_unique_writes']
        assert b[3]['writeback_superseded_drops']>0
    assert b[3]['writeback_buffer_array_bytes']==0


def tiny():
    return TSDFTile('t',np.array([[0.,1.],[0.,1.],[0.,1.]]),.25,np.eye(4),
        base_position_L=np.zeros(3),near_m=0,far_m=10)


def test_pending_is_private_and_flush_failure_keeps_retryable_state(tmp_path,monkeypatch):
    store=EpisodeStore(tmp_path/'episode','ep-writeback',dataset='r2r')
    with WriteBackReplayTileBacking(store) as backing:
        record=backing.save_tile(tiny());token=record['_pending_tile']
        with pytest.raises(IntegrityError,match='owned'):
            backing.load_tile(copy.deepcopy(record))
        original=backing.put_arrays
        def fail(arrays):raise OSError('encode/write fault')
        monkeypatch.setattr(backing,'put_arrays',fail)
        with pytest.raises(OSError):backing.promote([record])
        assert record['_pending_tile']==token and token in backing._buffer
        assert store.current is None
        monkeypatch.setattr(backing,'put_arrays',original)
        backing.promote([record])
        assert 'blob' in record and '_pending_tile' not in record
        assert not backing._buffer
        np.testing.assert_array_equal(store.load_tile(record).arrays()['weight'],0)
    store.close()


def test_prune_drops_superseded_without_encoding_and_exception_discards_scratch(tmp_path):
    store=EpisodeStore(tmp_path/'episode','ep-writeback',dataset='r2r')
    backing=WriteBackReplayTileBacking(store)
    with pytest.raises(RuntimeError):
        with backing:
            old=backing.save_tile(tiny());new=backing.save_tile(tiny())
            backing.prune([new])
            assert backing.metrics['writeback_superseded_drops']==1
            assert backing.metrics['staged_unique_writes']==0
            with pytest.raises(IntegrityError):backing.load_tile(old)
            raise RuntimeError('abort derived transaction')
    assert not backing._buffer and backing._buffer_bytes==0
    assert not backing._pending and backing._pending_bytes==0
    assert backing.metrics["writeback_pending_array_bytes"]==0
    assert backing.metrics["writeback_buffer_array_bytes"]==0
    assert store.current is None and not list((store.root/'.pending').glob('tile-replay-*'))
    store.close()


def test_bad_buffer_limit_rejected(tmp_path):
    store=EpisodeStore(tmp_path/'episode','ep-writeback',dataset='r2r')
    for budget in (-1,True,1.5):
        with pytest.raises(ValueError):WriteBackReplayTileBacking(store,max_buffer_bytes=budget)
    store.close()


def test_replacements_are_admitted_after_superseded_state_is_dropped(tmp_path):
    store=EpisodeStore(tmp_path/'episode','ep-writeback',dataset='r2r')
    size=sum(a.nbytes for a in tiny().arrays().values())
    with WriteBackReplayTileBacking(store,max_buffer_bytes=2*size,max_pending_tiles=2) as backing:
        old=[backing.save_tile(tiny()),backing.save_tile(tiny())]
        backing.prune(old)
        assert backing._buffer_bytes==2*size
        new=[backing.save_tile(tiny()),backing.save_tile(tiny())]
        # Existing source transaction owns both versions until it commits. The
        # write-back cache must not encode old versions to admit these writes.
        assert backing.metrics['writeback_flushes']==0
        assert backing._buffer_bytes==2*size and backing._pending_bytes==2*size
        for record in old:backing.load_tile(record)
        backing.prune(new)
        assert backing.metrics['writeback_superseded_drops']==2
        assert backing.metrics['writeback_flushes']==0 and backing._pending_bytes==0
        backing.promote(new)
        assert backing.metrics['writeback_flushes']==2
    store.close()


def test_failed_frame_can_discard_write_set_and_keep_old_records(tmp_path):
    from graphAdapter.map_memory.geometry.core import CapacityError
    store=EpisodeStore(tmp_path/'episode','ep-writeback',dataset='r2r')
    with WriteBackReplayTileBacking(store,max_pending_tiles=1) as backing:
        old=backing.save_tile(tiny());backing.prune([old])
        backing.save_tile(tiny())
        with pytest.raises(CapacityError,match='write set'):backing.save_tile(tiny())
        backing.prune([old])
        assert backing._pending_bytes==0
        np.testing.assert_array_equal(backing.load_tile(old).arrays()['weight'],0)
        assert backing.metrics['writeback_flushes']==0
        backing.promote([old])
    store.close()
