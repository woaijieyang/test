import numpy as np
import pytest
from graphAdapter.map_memory.storage.store import EpisodeStore,IntegrityError
from graphAdapter.map_memory.tests.test_storage import archive,EP,capture

def inputs():return dict(mask=np.ones((4,8,8),bool),xyxy=np.tile([0,0,8,8],(4,1))),dict(count=4,image_hw=[8,8])

def test_detection_batch_commits_once_and_exact_retry_does_not_write(tmp_path):
    store=EpisodeStore(tmp_path/'map',EP,dataset='r2r')
    try:
        archive(store,1);arrays,meta=inputs();trace=[];store.connection.set_trace_callback(trace.append)
        store.save_detections(capture(1)['frame_uid'],arrays,meta)
        assert sum(x.startswith('SAVEPOINT ') for x in trace)==1
        assert sum(x.startswith('RELEASE SAVEPOINT ') for x in trace)==1
        assert store.connection.execute('SELECT count(*) FROM detections').fetchone()[0]==4
        assert store.connection.execute('PRAGMA synchronous').fetchone()[0]==2
        trace.clear();store.save_detections(capture(1)['frame_uid'],arrays,meta)
        assert not any(x.startswith(('INSERT','UPDATE','DELETE')) for x in trace)
    finally:store.close()


def test_detection_batch_failure_rolls_back_and_reuses_durable_files(tmp_path,monkeypatch):
    store=EpisodeStore(tmp_path/'map',EP,dataset='r2r')
    try:
        archive(store,1);arrays,meta=inputs();original=store._insert_exact;calls=[]
        def fail(*args):
            calls.append(1)
            if len(calls)==3:raise OSError('injected row failure')
            return original(*args)
        monkeypatch.setattr(store,'_insert_exact',fail)
        with pytest.raises(OSError,match='row failure'):store.save_detections(capture(1)['frame_uid'],arrays,meta)
        assert store.connection.execute('SELECT count(*) FROM detections').fetchone()[0]==0
        files=list((store.root/'detections').iterdir());before={p.name:p.read_bytes() for p in files}
        assert len(files)==2
        monkeypatch.setattr(store,'_insert_exact',original)
        store.save_detections(capture(1)['frame_uid'],arrays,meta)
        assert store.connection.execute('SELECT count(*) FROM detections').fetchone()[0]==4
        assert before=={p.name:p.read_bytes() for p in files}
    finally:store.close()


def test_exact_row_conflict_still_rejected(tmp_path):
    store=EpisodeStore(tmp_path/'map',EP,dataset='r2r')
    try:
        archive(store,1);arrays,meta=inputs();store.save_detections(capture(1)['frame_uid'],arrays,meta)
        row=list(store.connection.execute('SELECT * FROM detections LIMIT 1').fetchone());row[-1]='different'
        with pytest.raises(IntegrityError,match='Immutable SQL'):store._insert_exact('detections',tuple(row),('uid',))
    finally:store.close()


def test_nested_detection_transaction_does_not_commit_caller_work(tmp_path):
    store=EpisodeStore(tmp_path/'map',EP,dataset='r2r')
    try:
        archive(store,1);arrays,meta=inputs();store.connection.execute('BEGIN IMMEDIATE')
        store.save_detections(capture(1)['frame_uid'],arrays,meta)
        assert store.connection.in_transaction
        store.connection.execute('ROLLBACK')
        assert store.connection.execute('SELECT count(*) FROM detections').fetchone()[0]==0
        store.save_detections(capture(1)['frame_uid'],arrays,meta)
        assert store.connection.execute('SELECT count(*) FROM detections').fetchone()[0]==4
    finally:store.close()


def test_post_commit_error_is_not_hidden_by_rollback(tmp_path):
    store=EpisodeStore(tmp_path/'map',EP,dataset='r2r')
    try:
        archive(store,1);arrays,meta=inputs();connection=store.connection
        class Proxy:
            raised=False
            def __getattr__(self,name):return getattr(connection,name)
            def execute(self,sql,*args):
                result=connection.execute(sql,*args)
                if sql.startswith('RELEASE SAVEPOINT') and not self.raised:
                    self.raised=True;raise OSError('post-commit injected error')
                return result
        store.connection=Proxy()
        with pytest.raises(OSError,match='post-commit injected'):store.save_detections(capture(1)['frame_uid'],arrays,meta)
        assert not connection.in_transaction
        assert connection.execute('SELECT count(*) FROM detections').fetchone()[0]==4
        store.save_detections(capture(1)['frame_uid'],arrays,meta)
    finally:store.close()
