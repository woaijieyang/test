from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parent))
from test_continuous_graph import item,seeded_service,seed_camera
from test_correction_channel import correction
from graphAdapter.map_memory.storage.store import EpisodeStore,load_episode
from graphAdapter.map_memory.correction_workspace import freeze_correction_job,materialize_correction_input


def test_detached_input_pins_prefix_while_active_writer_advances(tmp_path):
    p,a,m=item(1);store=EpisodeStore(tmp_path/'active','unit',dataset='r2r')
    try:
        service=seeded_service(store,p,a);service.ingest(p,**a,mapping_sample=m)
        with freeze_correction_job(service,correction(m)) as lease:
            base=service.pointer['snapshot_id']
            p2,a2,m2=item(2);seed_camera(service,p2,a2);service.ingest(p2,**a2,mapping_sample=m2)
            current=store.current['snapshot_id'];assert current!=base
            report=materialize_correction_input(lease.job,tmp_path/'detached')
            assert report['source_snapshot_id']==base and report['cutoff']['capture_seq']==1
            reader=load_episode(tmp_path/'detached')
            try:assert reader.verify()['views']==1
            finally:reader.close()
            assert (tmp_path/'detached/detections'/ (p.frame_uid+'.meta.json')).exists()
            assert store.current['snapshot_id']==current and store.current['cutoff']['capture_seq']==2
    finally:store.close()


def test_original_correction_builds_detached_without_touching_live_store(tmp_path):
    import numpy as np
    from graphAdapter.map_memory.correction_workspace import build_detached
    from graphAdapter.map_memory.service import GraphMapCorrectionConsumer
    packet,arrays,sample=item(1);store=EpisodeStore(tmp_path/'active','unit',dataset='r2r')
    try:
        service=seeded_service(store,packet,arrays);service.ingest(packet,**arrays,mapping_sample=sample)
        from dataclasses import replace
        from graphAdapter.map_memory.storage.store import canonical
        bindings=dict(sample.bindings);bindings['map_version']=2
        bindings['T_map_odom']=[list(row) for row in bindings['T_map_odom']]
        bindings['T_map_odom'][0][3]+=.25
        bindings['optimized_keyframes']={key:[list(row) for row in value] for key,value in bindings['optimized_keyframes'].items()}
        bindings['optimized_keyframes']['10'][0][3]+=.25
        target=replace(correction(sample),native_map_version=2,bindings_json=canonical(bindings))
        expected=GraphMapCorrectionConsumer('unit').resolve(service.frames[packet.frame_uid],target.bindings)
        with freeze_correction_job(service,target) as lease:
            p2,a2,m2=item(2);seed_camera(service,p2,a2);service.ingest(p2,**a2,mapping_sample=m2)
            before=(store.root/'CURRENT.json').read_bytes()
            result=build_detached(lease.job,tmp_path/'derived')
            assert result['detector_frames']==0 and not result['installed_in_active_store']
            assert result['target_provenance']==target.to_record()
            assert result['replayed_through']['capture_seq']==1
            reader=load_episode(tmp_path/'derived')
            try:
                np.testing.assert_array_equal(reader._graph['views'][packet.frame_uid]['T_G_base'],expected['T_G_base'])
                assert reader._graph['mapping_state']['correction_applied']
                historical=[row for row in reader._graph['entities'] if row.get('source_revision')]
                assert all(row['source_revision']==lease.job.record['base_snapshot_id'] for row in historical)
                import hashlib
                expected_epoch=hashlib.sha256(('unit|'+lease.job.record['base_snapshot_id']+'|'+str(target.native_map_version)).encode()).hexdigest()
                assert reader._graph['scene_state']['epoch']==expected_epoch
            finally:reader.close()
            assert (store.root/'CURRENT.json').read_bytes()==before
            assert len(service.frames)==2
    finally:store.close()


def test_correction_can_run_in_an_independent_process(tmp_path):
    import os,subprocess,sys
    packet,arrays,sample=item(1);store=EpisodeStore(tmp_path/'active','unit',dataset='r2r')
    try:
        service=seeded_service(store,packet,arrays);service.ingest(packet,**arrays,mapping_sample=sample)
        with freeze_correction_job(service,correction(sample)) as lease:
            job_path=tmp_path/'job.json';job_path.write_bytes(lease.job.payload_json)
            before=(store.root/'CURRENT.json').read_bytes()
            script=Path(__file__).parents[3]/'src/graphAdapter/map_memory/correction_workspace.py'
            result=subprocess.run([sys.executable,'-B',str(script),'--job',str(job_path),'--out',str(tmp_path/'child')],capture_output=True,text=True,timeout=60)
            assert result.returncode==0,result.stderr
            assert (tmp_path/'child/CORRECTION_RESULT.json').exists()
            assert (store.root/'CURRENT.json').read_bytes()==before
    finally:store.close()


def test_tail_uses_only_new_frozen_frames_and_preserves_original_target(tmp_path):
    from graphAdapter.map_memory.correction_workspace import build_detached,append_detached_tail
    from graphAdapter.map_memory.async_admission import FrozenObservation
    packet,arrays,sample=item(1);store=EpisodeStore(tmp_path/'active','unit',dataset='r2r')
    try:
        service=seeded_service(store,packet,arrays);service.ingest(packet,**arrays,mapping_sample=sample)
        target=correction(sample)
        with freeze_correction_job(service,target) as lease:
            p2,a2,m2=item(2);seed_camera(service,p2,a2);service.ingest(p2,**a2,mapping_sample=m2)
            tail=FrozenObservation.create(p2,a2['committed_receipt'],mapping_sample=m2,episode_instance=m2.episode_instance)
            source=store.open_reader()
            try:
                before=(store.root/'CURRENT.json').read_bytes()
                build_detached(lease.job,tmp_path/'derived')
                result=append_detached_tail(lease.job,tmp_path/'derived',[tail],source)
                assert result['target_provenance']==target.to_record()
                assert result['replayed_through']['capture_seq']==2
                assert result['detector_frames']==0 and result['appended'][0]['replayed_frames']==1
                assert (store.root/'CURRENT.json').read_bytes()==before
                reader=load_episode(tmp_path/'derived')
                try:assert reader.verify()['views']==2
                finally:reader.close()
            finally:source.close()
    finally:store.close()


def test_tail_lineage_accepts_only_the_complete_append_chain(tmp_path):
    import json,pytest
    from graphAdapter.map_memory.correction_workspace import validate_append_only_lineage
    from graphAdapter.map_memory.async_admission import FrozenObservation
    from graphAdapter.map_memory.storage.store import canonical,VersionUnavailable
    packet,arrays,sample=item(1);store=EpisodeStore(tmp_path/'active','unit',dataset='r2r')
    try:
        service=seeded_service(store,packet,arrays);service.ingest(packet,**arrays,mapping_sample=sample)
        with freeze_correction_job(service,correction(sample)) as lease:
            p2,a2,m2=item(2);seed_camera(service,p2,a2);service.ingest(p2,**a2,mapping_sample=m2)
            tail=FrozenObservation.create(p2,a2['committed_receipt'],mapping_sample=m2,episode_instance=m2.episode_instance)
            reader=store.open_reader()
            try:
                assert validate_append_only_lineage(lease.job,reader,[tail])['appends']==1
                with pytest.raises(VersionUnavailable):validate_append_only_lineage(lease.job,reader,[])
            finally:reader.close()
            newer=json.loads(canonical(service.graph));newer['scope']='same-cutoff update outside tail journal'
            store.publish(newer,{'pose_map_version':service.version},dict(store.current['cutoff']))
            reader=store.open_reader()
            try:
                with pytest.raises(VersionUnavailable,match='append journal'):
                    validate_append_only_lineage(lease.job,reader,[tail])
            finally:reader.close()
    finally:store.close()


def test_tail_rejects_unjournaled_update_before_workspace_mutation(tmp_path):
    import json,pytest
    from graphAdapter.map_memory.correction_workspace import build_detached,append_detached_tail
    from graphAdapter.map_memory.async_admission import FrozenObservation
    from graphAdapter.map_memory.storage.store import canonical,VersionUnavailable
    packet,arrays,sample=item(1);store=EpisodeStore(tmp_path/'active','unit',dataset='r2r')
    try:
        service=seeded_service(store,packet,arrays);service.ingest(packet,**arrays,mapping_sample=sample)
        with freeze_correction_job(service,correction(sample)) as lease:
            build_detached(lease.job,tmp_path/'derived')
            p2,a2,m2=item(2);seed_camera(service,p2,a2);service.ingest(p2,**a2,mapping_sample=m2)
            tail=FrozenObservation.create(p2,a2['committed_receipt'],mapping_sample=m2,episode_instance=m2.episode_instance)
            newer=json.loads(canonical(service.graph));newer['scope']='unexpected update'
            store.publish(newer,{'pose_map_version':service.version},dict(store.current['cutoff']))
            before=(tmp_path/'derived/CURRENT.json').read_bytes();reader=store.open_reader()
            try:
                with pytest.raises(VersionUnavailable,match='append journal'):
                    append_detached_tail(lease.job,tmp_path/'derived',[tail],reader)
                assert (tmp_path/'derived/CURRENT.json').read_bytes()==before
            finally:reader.close()
    finally:store.close()


def test_incremental_catchup_reuses_previous_tail(tmp_path):
    from graphAdapter.map_memory.correction_workspace import build_detached,append_detached_tail
    from graphAdapter.map_memory.async_admission import FrozenObservation
    packet,arrays,sample=item(1);store=EpisodeStore(tmp_path/'active','unit',dataset='r2r')
    try:
        service=seeded_service(store,packet,arrays);service.ingest(packet,**arrays,mapping_sample=sample)
        with freeze_correction_job(service,correction(sample)) as lease:
            build_detached(lease.job,tmp_path/'derived');journal=[]
            for seq in (2,3):
                p,a,m=item(seq);seed_camera(service,p,a);service.ingest(p,**a,mapping_sample=m)
                frozen=FrozenObservation.create(p,a['committed_receipt'],mapping_sample=m,episode_instance=m.episode_instance)
                journal.append(frozen);reader=store.open_reader()
                try:
                    report=append_detached_tail(lease.job,tmp_path/'derived',[frozen],reader,append_journal=journal)
                    assert report['source_lineage']['appends']==seq-1
                    assert len(report['appended'])==1 and report['appended'][0]['replayed_frames']==1
                    assert report['replayed_through']['capture_seq']==seq and report['detector_frames']==0
                finally:reader.close()
            reader=load_episode(tmp_path/'derived')
            try:assert reader.verify()['views']==3
            finally:reader.close()
    finally:store.close()


import pytest
@pytest.mark.parametrize('fail_after_publish',[False,True])
@pytest.mark.parametrize('prestage',[False,True])
def test_install_caught_up_result_and_continue_mapping(tmp_path,fail_after_publish,prestage,monkeypatch):
    import numpy as np
    from dataclasses import replace
    from graphAdapter.map_memory.storage.store import canonical
    from graphAdapter.map_memory.correction_workspace import build_detached,append_detached_tail,install_detached
    from graphAdapter.map_memory.async_admission import FrozenObservation
    packet,arrays,sample=item(1);store=EpisodeStore(tmp_path/'active','unit',dataset='r2r')
    try:
        service=seeded_service(store,packet,arrays);service.ingest(packet,**arrays,mapping_sample=sample)
        bindings=dict(sample.bindings);bindings['map_version']=2
        bindings['T_map_odom']=[list(row) for row in bindings['T_map_odom']];bindings['T_map_odom'][0][3]+=.25
        bindings['optimized_keyframes']={k:[list(row) for row in v] for k,v in bindings['optimized_keyframes'].items()}
        bindings['optimized_keyframes']['10'][0][3]+=.25
        target=replace(correction(sample),native_map_version=2,bindings_json=canonical(bindings))
        with freeze_correction_job(service,target) as lease:
            build_detached(lease.job,tmp_path/'derived')
            p2,a2,m2=item(2);seed_camera(service,p2,a2);service.ingest(p2,**a2,mapping_sample=m2)
            tail=FrozenObservation.create(p2,a2['committed_receipt'],mapping_sample=m2,episode_instance=m2.episode_instance)
            reader=store.open_reader()
            try:append_detached_tail(lease.job,tmp_path/'derived',[tail],reader)
            finally:reader.close()
            previous=service.pointer['snapshot_id']
            if prestage:
                import shutil
                from graphAdapter.map_memory.correction_workspace import stage_detached_blobs
                before=(store.root/'CURRENT.json').read_bytes()
                import subprocess,json
                job_path=tmp_path/'stage-job.json';job_path.write_bytes(lease.job.payload_json)
                script=Path(__file__).parents[3]/'src/graphAdapter/map_memory/correction_workspace.py'
                child=subprocess.run([sys.executable,'-B',str(script),'--job',str(job_path),
                    '--out',str(tmp_path/'derived'),'--stage-only'],capture_output=True,text=True,timeout=60)
                assert child.returncode==0,child.stderr
                staged=json.loads(child.stdout.strip().splitlines()[-1])
                assert staged['imported_blobs']>0 and staged['published'] is False
                assert (store.root/'CURRENT.json').read_bytes()==before
                def forbidden_copy(*args,**kwargs):raise AssertionError('Installation recopied prestaged data')
                monkeypatch.setattr(shutil,'copyfileobj',forbidden_copy)
            def fault(stage):
                if stage=='current_replaced':raise RuntimeError('injected after visibility')
            if fail_after_publish:
                with pytest.raises(RuntimeError,match='injected'):
                    install_detached(service,lease.job,tmp_path/'derived',[tail],fault=fault)
            else:
                report=install_detached(service,lease.job,tmp_path/'derived',[tail])
                assert report['installed_in_active_store'] and report['parent_snapshot_id']==previous
                if prestage:assert report['imported_blobs']==0 and report['reused_blobs']>0
            assert service.pointer==store.current and service.pointer['snapshot_id']!=previous
            assert service.version==2 and len(service.frames)==2
            reader=load_episode(tmp_path/'derived')
            try:
                for uid in reader._graph['views']:
                    np.testing.assert_array_equal(service.graph['views'][uid]['T_G_base'],reader._graph['views'][uid]['T_G_base'])
            finally:reader.close()
            p3,a3,m3=item(3);seed_camera(service,p3,a3)
            outcome=service.ingest(p3,**a3,mapping_sample=m3,apply_mapping_correction=False)
            assert outcome['replayed_frames']==1 and not outcome['rebuild']
            reader=store.open_reader()
            try:assert reader.verify()['views']==3
            finally:reader.close()
    finally:store.close()


def test_page_cache_hit_reuses_measured_size_but_force_rechecks(tmp_path,monkeypatch):
    import graphAdapter.map_memory.storage.pages as pages
    packet,arrays,sample=item(1);store=EpisodeStore(tmp_path/'active','unit',dataset='r2r')
    try:
        service=seeded_service(store,packet,arrays);service.ingest(packet,**arrays,mapping_sample=sample)
        reader=store.open_reader()
        try:
            measured=[];original=pages.deep_size
            def measure(value):measured.append(id(value));return original(value)
            monkeypatch.setattr(pages,'deep_size',measure)
            pager=reader.pages;key=pager.root_node
            first=pager.node(key,force=True);size=pager.bytes;calls=len(measured);reads=pager.read_bytes
            assert calls>0 and key in pager.cache
            for _ in range(10):assert pager.node(key) is first
            assert len(measured)==calls and pager.bytes==size and pager.read_bytes==reads
            pager.node(key,force=True)
            assert len(measured)==calls+1 and pager.read_bytes>reads
            assert pager.bytes==sum(n for _,n in pager.cache.values()) and pager.bytes<=pager.limit
        finally:reader.close()
    finally:store.close()


def test_install_rejects_base_advanced_during_blob_preparation(tmp_path,monkeypatch):
    import graphAdapter.map_memory.correction_workspace as workspace
    from graphAdapter.map_memory.async_admission import FrozenObservation
    from graphAdapter.map_memory.storage import store as storage
    packet,arrays,sample=item(1);store=EpisodeStore(tmp_path/'active','unit',dataset='r2r')
    try:
        service=seeded_service(store,packet,arrays);service.ingest(packet,**arrays,mapping_sample=sample)
        with freeze_correction_job(service,correction(sample)) as lease:
            workspace.build_detached(lease.job,tmp_path/'derived')
            p2,a2,m2=item(2);seed_camera(service,p2,a2);service.ingest(p2,**a2,mapping_sample=m2)
            frozen=FrozenObservation.create(p2,a2['committed_receipt'],mapping_sample=m2,episode_instance=m2.episode_instance)
            reader=store.open_reader()
            try:workspace.append_detached_tail(lease.job,tmp_path/'derived',[frozen],reader)
            finally:reader.close()
            original=workspace._import_immutable_graph;advanced=[]
            def import_then_advance(*args,**kwargs):
                result=original(*args,**kwargs)
                p3,a3,m3=item(3);seed_camera(service,p3,a3)
                service.ingest(p3,**a3,mapping_sample=m3,apply_mapping_correction=False)
                advanced.append(service.pointer['snapshot_id']);return result
            monkeypatch.setattr(workspace,'_import_immutable_graph',import_then_advance)
            with pytest.raises(storage.legacy.ConcurrentWriterError,match='base'):
                workspace.install_detached(service,lease.job,tmp_path/'derived',[frozen])
            assert len(advanced)==1 and service.pointer['snapshot_id']==advanced[0]
            assert service.pointer==store.current and service.pointer['cutoff']['capture_seq']==3
            reader=store.open_reader()
            try:assert reader.verify()['views']==3
            finally:reader.close()
    finally:store.close()


def test_background_channel_allows_foreground_append_and_single_flight(tmp_path):
    import time
    from graphAdapter.map_memory.correction_process import BackgroundCorrectionChannel
    packet,arrays,sample=item(1);store=EpisodeStore(tmp_path/'active','unit',dataset='r2r');channel=BackgroundCorrectionChannel()
    try:
        service=seeded_service(store,packet,arrays);service.ingest(packet,**arrays,mapping_sample=sample)
        status=channel.start(service,correction(sample),tmp_path/'background')
        assert status['state']=='RUNNING' and channel.lease.reader is not None
        with pytest.raises(RuntimeError,match='Previous correction'):
            channel.start(service,correction(sample),tmp_path/'second')
        p2,a2,m2=item(2);seed_camera(service,p2,a2);service.ingest(p2,**a2,mapping_sample=m2)
        current=service.pointer['snapshot_id'];deadline=time.monotonic()+40
        while channel.poll()['state']=='RUNNING' and time.monotonic()<deadline:time.sleep(.02)
        outcome=channel.poll();assert outcome['state']=='READY',outcome
        assert channel.lease is None and channel.process.poll() is None
        assert store.current['snapshot_id']==current and store.current['cutoff']['capture_seq']==2
        assert outcome['result']['replayed_through']['capture_seq']==1
        assert channel.collect()['installed_in_active_store'] is False
        assert channel.poll()['state']=='IDLE'
        from graphAdapter.map_memory.correction_workspace import CorrectionJob,install_detached
        from graphAdapter.map_memory.async_admission import FrozenObservation
        job=CorrectionJob((tmp_path/'background/job.json').read_bytes())
        from graphAdapter.map_memory.tail_journal import FrozenTailJournal
        with FrozenTailJournal(tmp_path/'durable-tail',job,max_bytes=1000000,max_entries=10) as durable:
            reader=store.open_reader()
            try:durable.append(FrozenObservation.create(p2,a2['committed_receipt'],mapping_sample=m2,episode_instance=m2.episode_instance),reader)
            finally:reader.close()
            journal=durable.snapshot()
        channel.start_catchup(service,job,tmp_path/'background/map',journal,tmp_path/'catchup2')
        p3,a3,m3=item(3);seed_camera(service,p3,a3);service.ingest(p3,**a3,mapping_sample=m3)
        with FrozenTailJournal(tmp_path/'durable-tail',job,max_bytes=1000000,max_entries=10) as durable:
            reader=store.open_reader()
            try:durable.append(FrozenObservation.create(p3,a3['committed_receipt'],mapping_sample=m3,episode_instance=m3.episode_instance),reader)
            finally:reader.close()
            journal=durable.snapshot()
        deadline=time.monotonic()+40
        while channel.poll()['state']=='RUNNING' and time.monotonic()<deadline:time.sleep(.02)
        caught=channel.collect();assert caught['state']=='READY',caught
        assert caught['result']['replayed_through']['capture_seq']==2
        assert len(caught['result']['appended'])==1 and caught['result']['appended'][0]['replayed_frames']==1
        assert service.pointer['cutoff']['capture_seq']==3
        channel.start_catchup(service,job,tmp_path/'background/map',journal,tmp_path/'catchup3')
        deadline=time.monotonic()+40
        while channel.poll()['state']=='RUNNING' and time.monotonic()<deadline:time.sleep(.02)
        caught=channel.collect();assert caught['state']=='READY',caught
        assert caught['service_creations']==1 and caught['service_reuses']==2
        assert len(caught['result']['appended'])==1 and caught['result']['appended'][0]['replayed_frames']==1
        installed=install_detached(service,job,tmp_path/'background/map',journal)
        assert installed['cutoff']['capture_seq']==3 and installed['imported_blobs']==0
        assert channel.spawn_count==1 and channel.process.poll() is None
        before=(store.root/'CURRENT.json').read_bytes();pid=channel.process.pid
        channel.start_release(service,job,tmp_path/'background/map',tmp_path/'release')
        deadline=time.monotonic()+40
        while channel.poll()['state']=='RUNNING' and time.monotonic()<deadline:time.sleep(.02)
        released=channel.collect();assert released['state']=='READY',released
        assert released['result']['workspace_closed'] and released['result']['release_audit']['memory_closed']
        assert released['result']['release_audit']['pins_zero']
        reopened=EpisodeStore(tmp_path/'background/map','unit',dataset='r2r',create=False);reopened.close()
        from graphAdapter.map_memory.correction_cleanup import reclaim_workspace
        pinned=load_episode(tmp_path/'background/map')
        try:
            with pytest.raises(BlockingIOError):reclaim_workspace(service,job,tmp_path/'background/map',installed)
            assert (tmp_path/'background/map/CURRENT.json').exists()
        finally:pinned.close()
        reclaimed=reclaim_workspace(service,job,tmp_path/'background/map',installed)
        assert reclaimed['status']=='RECLAIMED_PRIVATE_COMPUTE_MAP'
        assert not (tmp_path/'background/map').exists() and (tmp_path/'background/RECLAIMED.json').exists()
        assert (store.root/'CURRENT.json').read_bytes()==before
        channel.start(service,correction(m3),tmp_path/'next-build')
        deadline=time.monotonic()+40
        while channel.poll()['state']=='RUNNING' and time.monotonic()<deadline:time.sleep(.02)
        next_job=channel.collect();assert next_job['state']=='READY',next_job
        assert channel.process.pid==pid and channel.spawn_count==1 and next_job['service_creations']==2
        reader=store.open_reader()
        try:assert reader.verify()['views']==3
        finally:reader.close()
    finally:channel.close();store.close()


def test_background_close_observes_exit_before_releasing_pin(tmp_path):
    from graphAdapter.map_memory.correction_process import BackgroundCorrectionChannel
    packet,arrays,sample=item(1);store=EpisodeStore(tmp_path/'active','unit',dataset='r2r');channel=BackgroundCorrectionChannel()
    try:
        service=seeded_service(store,packet,arrays);service.ingest(packet,**arrays,mapping_sample=sample)
        before=(store.root/'CURRENT.json').read_bytes()
        channel.start(service,correction(sample),tmp_path/'background');child=channel.process
        outcome=channel.close()
        assert child.poll() is not None and channel.lease is None
        assert outcome['state'] in ('ABORTED','READY') and outcome['installed_in_active_store'] is False
        assert (store.root/'CURRENT.json').read_bytes()==before
    finally:channel.close();store.close()


def test_background_launch_failure_releases_lease(tmp_path,monkeypatch):
    import graphAdapter.map_memory.correction_process as process
    packet,arrays,sample=item(1);store=EpisodeStore(tmp_path/'active','unit',dataset='r2r');channel=process.BackgroundCorrectionChannel()
    try:
        service=seeded_service(store,packet,arrays);service.ingest(packet,**arrays,mapping_sample=sample)
        leases=[];original=process.freeze_correction_job
        def freeze(*args):
            value=original(*args);leases.append(value);return value
        def fail(*args,**kwargs):raise OSError('injected launch failure')
        monkeypatch.setattr(process,'freeze_correction_job',freeze);monkeypatch.setattr(process.subprocess,'Popen',fail)
        with pytest.raises(OSError,match='launch failure'):channel.start(service,correction(sample),tmp_path/'background')
        assert leases[0].reader is None and channel.log is None and channel.poll()['state']=='IDLE'
    finally:channel.close();store.close()


def test_background_catchup_budget_and_missing_workspace_fail_closed(tmp_path):
    import time
    from graphAdapter.map_memory.correction_process import BackgroundCorrectionChannel
    packet,arrays,sample=item(1);store=EpisodeStore(tmp_path/'active','unit',dataset='r2r');channel=BackgroundCorrectionChannel()
    try:
        service=seeded_service(store,packet,arrays);service.ingest(packet,**arrays,mapping_sample=sample)
        with freeze_correction_job(service,correction(sample)) as lease:job=lease.job
        before=(store.root/'CURRENT.json').read_bytes()
        with pytest.raises(ValueError,match='byte budget'):
            channel.start_catchup(service,job,tmp_path/'missing',[],tmp_path/'too-large',max_journal_bytes=1)
        assert channel.poll()['state']=='IDLE' and not (tmp_path/'too-large').exists()
        channel.start_catchup(service,job,tmp_path/'missing',[],tmp_path/'failed-child')
        deadline=time.monotonic()+40
        while channel.poll()['state']=='RUNNING' and time.monotonic()<deadline:time.sleep(.02)
        outcome=channel.collect()
        assert outcome['state']=='FAILED' and outcome['phase_exit_code']==1 and outcome['returncode'] is None and outcome['installed_in_active_store'] is False
        assert channel.lease is None and channel.process.poll() is None
        assert (store.root/'CURRENT.json').read_bytes()==before
    finally:channel.close();store.close()


def test_durable_tail_journal_reopen_retry_capacity_and_corruption(tmp_path):
    import json
    from graphAdapter.map_memory.tail_journal import FrozenTailJournal
    from graphAdapter.map_memory.async_admission import FrozenObservation
    from graphAdapter.map_memory.storage.store import IntegrityError
    packet,arrays,sample=item(1);store=EpisodeStore(tmp_path/'active','unit',dataset='r2r')
    try:
        service=seeded_service(store,packet,arrays);service.ingest(packet,**arrays,mapping_sample=sample)
        with freeze_correction_job(service,correction(sample)) as lease:job=lease.job
        p2,a2,m2=item(2);seed_camera(service,p2,a2);service.ingest(p2,**a2,mapping_sample=m2)
        frozen=FrozenObservation.create(p2,a2['committed_receipt'],mapping_sample=m2,episode_instance=m2.episode_instance)
        reader=store.open_reader()
        try:
            with FrozenTailJournal(tmp_path/'journal',job,max_bytes=1000000,max_entries=1) as journal:
                assert journal.append(frozen,reader) is True
                before=(tmp_path/'journal/entries/0000000002.json').read_bytes()
                assert journal.append(frozen,reader) is False
                assert (tmp_path/'journal/entries/0000000002.json').read_bytes()==before
                with pytest.raises(BlockingIOError):FrozenTailJournal(tmp_path/'journal',job,max_bytes=1000000,max_entries=1)
            with FrozenTailJournal(tmp_path/'journal',job,max_bytes=1000000,max_entries=1) as journal:
                assert journal.snapshot()[0].packet_json==frozen.packet_json
                assert journal.snapshot()[0].mapping_json==frozen.mapping_json
                assert journal.append(frozen,reader) is False
                p3,a3,m3=item(3);seed_camera(service,p3,a3);service.ingest(p3,**a3,mapping_sample=m3)
                new=FrozenObservation.create(p3,a3['committed_receipt'],mapping_sample=m3,episode_instance=m3.episode_instance)
                latest=store.open_reader()
                try:
                    with pytest.raises(ValueError,match='capacity'):journal.append(new,latest)
                    assert len(journal.snapshot())==1 and service.pointer['cutoff']['capture_seq']==3
                finally:latest.close()
        finally:reader.close()
        path=tmp_path/'journal/entries/0000000002.json';value=json.loads(path.read_bytes())
        value['body']['snapshot_id']='corrupted';path.write_text(json.dumps(value))
        with pytest.raises(IntegrityError,match='hash chain'):
            FrozenTailJournal(tmp_path/'journal',job,max_bytes=1000000,max_entries=1)
    finally:store.close()


@pytest.mark.parametrize('graph_committed',[False,True])
def test_frozen_intent_recovers_crash_on_either_side_of_publication(tmp_path,graph_committed):
    from graphAdapter.map_memory.tail_journal import FrozenTailJournal
    from graphAdapter.map_memory.async_admission import FrozenObservation
    packet,arrays,sample=item(1);store=EpisodeStore(tmp_path/'active','unit',dataset='r2r')
    try:
        service=seeded_service(store,packet,arrays);service.ingest(packet,**arrays,mapping_sample=sample)
        with freeze_correction_job(service,correction(sample)) as lease:job=lease.job
        p2,a2,m2=item(2);seed_camera(service,p2,a2)
        frozen=FrozenObservation.create(p2,a2['committed_receipt'],mapping_sample=m2,episode_instance=m2.episode_instance)
        with FrozenTailJournal(tmp_path/'journal',job,max_bytes=1000000,max_entries=2) as journal:
            journal.prepare(frozen)
            assert len(journal.snapshot())==0 and journal.pending().mapping_json==frozen.mapping_json
            if graph_committed:service.ingest(p2,**a2,mapping_sample=m2)
        # Reopen at the crash window: intent is durable, binding is absent.
        before=(store.root/'CURRENT.json').read_bytes()
        with FrozenTailJournal(tmp_path/'journal',job,max_bytes=1000000,max_entries=2) as journal:
            reader=store.open_reader()
            try:assert journal.reconcile(reader) is graph_committed
            finally:reader.close()
            assert (store.root/'CURRENT.json').read_bytes()==before
            if not graph_committed:
                assert journal.pending().packet_json==frozen.packet_json
                service.ingest(p2,**a2,mapping_sample=journal.pending().mapping_sample)
                reader=store.open_reader()
                try:assert journal.reconcile(reader) is True
                finally:reader.close()
            assert journal.pending() is None and len(journal.snapshot())==1
            assert journal.snapshot()[0].mapping_json==frozen.mapping_json
            reader=store.open_reader()
            try:assert journal.reconcile(reader) is False
            finally:reader.close()
        assert store.current['cutoff']['capture_seq']==2
    finally:store.close()


@pytest.mark.parametrize('failure_stage',[None,'before_sql_commit','current_replaced'])
def test_service_publication_owns_frozen_intent_lifecycle(tmp_path,failure_stage):
    from graphAdapter.map_memory.tail_journal import FrozenTailJournal
    packet,arrays,sample=item(1);store=EpisodeStore(tmp_path/'active','unit',dataset='r2r');journal=None
    try:
        service=seeded_service(store,packet,arrays);service.ingest(packet,**arrays,mapping_sample=sample)
        with freeze_correction_job(service,correction(sample)) as lease:job=lease.job
        journal=FrozenTailJournal(tmp_path/'journal',job,max_bytes=1000000,max_entries=4)
        service.attach_tail_journal(journal)
        p2,a2,m2=item(2);seed_camera(service,p2,a2)
        ready=service.prepare_endpoint(p2,**a2,mapping_sample=m2,apply_mapping_correction=False)
        assert journal.pending().packet.frame_uid==p2.frame_uid and store.current['cutoff']['capture_seq']==1
        def fault(stage):
            if stage==failure_stage:raise RuntimeError('injected publication failure')
        if failure_stage is None:
            service.publish_prepared(frame_uid=ready['frame_uid'],target_pose_map_version=ready['target_pose_map_version'])
        else:
            with pytest.raises(RuntimeError,match='injected publication'):
                service.publish_prepared(frame_uid=ready['frame_uid'],target_pose_map_version=ready['target_pose_map_version'],fault=fault)
        committed=failure_stage!='before_sql_commit'
        assert len(journal.snapshot())==int(committed)
        assert (journal.pending() is None)==committed
        assert service.pointer==store.current
        service.detach_tail_journal();journal.close()
        journal=FrozenTailJournal(tmp_path/'journal',job,max_bytes=1000000,max_entries=4)
        service.attach_tail_journal(journal)
        if not committed:service.ingest(p2,**a2,mapping_sample=m2,apply_mapping_correction=False)
        assert len(journal.snapshot())==1 and journal.pending() is None
        before=service.pointer['snapshot_id']
        assert service.ingest(p2,**a2,mapping_sample=m2,apply_mapping_correction=False)['duplicate']
        assert service.pointer['snapshot_id']==before and len(journal.snapshot())==1
        service.detach_tail_journal()
    finally:
        if journal is not None:journal.close()
        store.close()


def test_scheduler_runs_full_lifecycle_without_replaying_committed_tail(tmp_path):
    import json
    from dataclasses import replace
    from graphAdapter.map_memory.storage.store import canonical
    from graphAdapter.map_memory.correction_scheduler import DetachedCorrectionScheduler
    packet,arrays,sample=item(1);store=EpisodeStore(tmp_path/'active','unit',dataset='r2r');scheduler=None
    try:
        service=seeded_service(store,packet,arrays);service.ingest(packet,**arrays,mapping_sample=sample)
        bindings=json.loads(canonical(sample.bindings));bindings['map_version']=2
        bindings['T_map_odom'][0][3]+=.25;bindings['optimized_keyframes']['10'][0][3]+=.25
        target=replace(correction(sample),native_map_version=2,bindings_json=canonical(bindings))
        scheduler=DetachedCorrectionScheduler(service,tmp_path/'scheduler',journal_bytes=1000000,journal_entries=10)
        assert scheduler.request(target)['started']
        assert not scheduler.request(target)['started']
        for seq in (2,3):
            p,a,m=item(seq);seed_camera(service,p,a)
            ready=service.ingest(p,**a,mapping_sample=m,apply_mapping_correction=False)
            assert ready['replayed_frames']==1 and not ready['rebuild']
        assert len(scheduler.journal.snapshot())==2
        scheduler.drain(timeout=50)
        assert service.tail_journal is None and service.version==2
        assert scheduler.channel.spawn_count==1
        publication=scheduler.collect_publication()
        assert publication['cutoff']['capture_seq']==3 and publication['imported_blobs']==0
        assert publication['target_provenance']==target.to_record()
        assert scheduler.collect_publication() is None
        receipts=list((tmp_path/'scheduler/job-000001').glob('catchup-*/PROCESS_OUTCOME.json'))
        assert len(receipts)==1
        tail=json.loads(receipts[0].read_bytes())['result']
        assert not (tmp_path/'scheduler/job-000001/build/map').exists()
        assert (tmp_path/'scheduler/job-000001/build/RECLAIMED.json').exists()
        assert [x['replayed_frames'] for x in tail['appended']]==[1,1]
        p,a,m=item(4);seed_camera(service,p,a);ready=service.ingest(p,**a,mapping_sample=m,apply_mapping_correction=False)
        assert ready['replayed_frames']==1 and not ready['rebuild']
        reader=store.open_reader()
        try:assert reader.verify()['views']==4
        finally:reader.close()
    finally:
        if scheduler is not None:scheduler.close()
        store.close()


def test_scheduler_abort_releases_owned_resources_without_publication(tmp_path):
    from graphAdapter.map_memory.correction_scheduler import DetachedCorrectionScheduler
    packet,arrays,sample=item(1);store=EpisodeStore(tmp_path/'active','unit',dataset='r2r');scheduler=None
    try:
        service=seeded_service(store,packet,arrays);service.ingest(packet,**arrays,mapping_sample=sample)
        before=(store.root/'CURRENT.json').read_bytes()
        scheduler=DetachedCorrectionScheduler(service,tmp_path/'scheduler',journal_bytes=1000000,journal_entries=10)
        scheduler.request(correction(sample));child=scheduler.channel.process
        result=scheduler.close()
        assert child.poll() is not None and result['closed']
        assert service.tail_journal is None and scheduler.journal is None
        assert (store.root/'CURRENT.json').read_bytes()==before
    finally:
        if scheduler is not None:scheduler.close()
        store.close()


def test_worker_background_controller_delivers_terminal_receipts(tmp_path):
    from graphAdapter.map_memory.correction_scheduler import WorkerCorrectionController
    packet,arrays,sample=item(1);store=EpisodeStore(tmp_path/'active','unit',dataset='r2r');controller=None
    try:
        service=seeded_service(store,packet,arrays);service.ingest(packet,**arrays,mapping_sample=sample)
        controller=WorkerCorrectionController(service,tmp_path/'worker-background',dict(journal_bytes=1000000,journal_entries=10,drain_timeout_s=50))
        controller.after_observation_commit(correction(sample))
        with pytest.raises(RuntimeError,match='drain'):controller.assert_drained()
        result=controller.finish(correction(sample))
        assert result['duplicate'] and len(result['prior_publications'])==1
        receipt=result['prior_publications'][0]
        assert receipt['snapshot_id']==service.pointer['snapshot_id'] and receipt['frontier_packet']==packet.to_record()
        assert controller.receipts()==result['prior_publications']
        with pytest.raises(RuntimeError,match='drain'):controller.assert_drained()
        controller.acknowledge_sent();controller.assert_drained()
        again=controller.finish(correction(sample))
        assert again['duplicate'] and again['prior_publications']==[]
        first_pid=controller.scheduler.channel.process.pid
        p2,a2,m2=item(2);seed_camera(service,p2,a2);service.ingest(p2,**a2,mapping_sample=m2)
        controller.after_observation_commit(correction(m2));second=controller.finish(correction(m2))
        assert len(second['prior_publications'])==1
        assert controller.scheduler.channel.process.pid==first_pid and controller.scheduler.channel.spawn_count==1
        assert second['versions']['pose_map_version']==m2.native_map_version
        controller.acknowledge_sent();controller.assert_drained()
    finally:
        if controller is not None:controller.close()
        store.close()


def test_background_profile_requires_live_async_and_declared_limits():
    from graphAdapter.map_memory.worker import validate_mapping_profile
    base=dict(pose_input_mode='continuous',async_admission=True,correction=dict(max_correction_difference_m=.025,mapping_point_radius_m=5.),
        background_correction=dict(enabled=True,journal_bytes=1000000,journal_entries=10,drain_timeout_s=50))
    assert validate_mapping_profile(base)=='continuous'
    for field,value in [('async_admission',False),('execution_mode','archive_only'),('pose_input_mode','native_corrected')]:
        with pytest.raises(ValueError,match='continuous live async'):validate_mapping_profile(dict(base,**{field:value}))
    with pytest.raises(ValueError,match='limit'):
        validate_mapping_profile(dict(base,background_correction=dict(enabled=True)))


def test_correction_runtime_rejects_absent_or_mismatched_protection(monkeypatch):
    import os,json
    from graphAdapter.map_memory.correction_runtime import require_correction_runtime
    monkeypatch.delenv('GRAPH_MEMORY_PRIVATE_RUNTIME',raising=False)
    monkeypatch.delenv('CASE1_PROTECTION',raising=False)
    with pytest.raises(RuntimeError,match='protected runtime'):require_correction_runtime()
    monkeypatch.setenv('CASE1_PROTECTION',json.dumps(dict(landlock_abi=3,readonly_mount=True)))
    assert require_correction_runtime()['kind']=='host_protected_runtime'
    monkeypatch.setenv('GRAPH_MEMORY_PRIVATE_RUNTIME',json.dumps(dict(kind='memory_worker_bwrap',owner_pid=os.getpid(),mount_namespace='wrong')))
    with pytest.raises(RuntimeError,match='namespace'):require_correction_runtime()
    monkeypatch.setenv('GRAPH_MEMORY_PRIVATE_RUNTIME',json.dumps(dict(kind='memory_worker_bwrap',owner_pid=-1,mount_namespace=os.readlink('/proc/self/ns/mnt'))))
    with pytest.raises(RuntimeError,match='owned'):require_correction_runtime()


def test_cleanup_failure_preserves_already_committed_publication(tmp_path,monkeypatch):
    from graphAdapter.map_memory.correction_scheduler import WorkerCorrectionController
    import graphAdapter.map_memory.correction_cleanup as cleanup
    packet,arrays,sample=item(1);store=EpisodeStore(tmp_path/'active','unit',dataset='r2r');controller=None
    try:
        service=seeded_service(store,packet,arrays);service.ingest(packet,**arrays,mapping_sample=sample)
        original=service.pointer['snapshot_id']
        controller=WorkerCorrectionController(service,tmp_path/'controller',dict(journal_bytes=1000000,journal_entries=10,drain_timeout_s=50))
        def fail(*args,**kwargs):raise OSError('injected reclamation failure')
        monkeypatch.setattr(cleanup,'reclaim_workspace',fail)
        controller.after_observation_commit(correction(sample))
        with pytest.raises(OSError,match='reclamation'):controller.finish(correction(sample))
        receipts=controller.receipts();assert len(receipts)==1
        assert receipts[0]['snapshot_id']==service.pointer['snapshot_id']!=original
        assert (tmp_path/'controller/job-000001/build/map/CURRENT.json').exists()
        assert service.tail_journal is None
    finally:
        if controller is not None:controller.close()
        store.close()


def test_terminal_threshold_retains_map_without_false_applied_revision(tmp_path):
    from graphAdapter.map_memory.correction_scheduler import WorkerCorrectionController
    p,a,m=item(1);store=EpisodeStore(tmp_path/'active','unit',dataset='r2r');controller=None
    try:
        service=seeded_service(store,p,a);service.ingest(p,**a,mapping_sample=m)
        p2,a2,m2=item(2);seed_camera(service,p2,a2);service.ingest(p2,**a2,mapping_sample=m2)
        before=(store.root/'CURRENT.json').read_bytes()
        controller=WorkerCorrectionController(service,tmp_path/'controller',dict(journal_bytes=1000000,journal_entries=10,drain_timeout_s=30,max_correction_difference_m=.025,mapping_point_radius_m=5.))
        result=controller.finish(correction(m2))
        assert result['correction_assessment']['action']=='retain'
        assert result['versions']['pose_map_version']==1 and result['correction_assessment']['native_target_version']==2
        assert result['prior_publications']==[] and controller.scheduler.channel.spawn_count==0
        assert (store.root/'CURRENT.json').read_bytes()==before
    finally:
        if controller:controller.close()
        store.close()


def test_terminal_threshold_includes_rotational_displacement(tmp_path):
    import json,numpy as np
    from dataclasses import replace
    from graphAdapter.map_memory.storage.store import canonical
    p,a,m=item(1);store=EpisodeStore(tmp_path/'active','unit',dataset='r2r')
    try:
        service=seeded_service(store,p,a);service.ingest(p,**a,mapping_sample=m)
        binding=json.loads(canonical(m.bindings));binding['map_version']=2
        angle=.02;rot=np.array([[np.cos(angle),-np.sin(angle),0],[np.sin(angle),np.cos(angle),0],[0,0,1.]])
        for matrix in [binding['T_map_odom'],binding['optimized_keyframes']['10']]:
            for row in range(3):matrix[row][:3]=rot[row].tolist()
        target=replace(correction(m),native_map_version=2,bindings_json=canonical(binding))
        result=service.assess_terminal_correction(target,max_difference_m=.025,point_radius_m=5.)
        assert result['action']=='correct' and p.frame_uid in result['affected_frame_uids']
    finally:store.close()
