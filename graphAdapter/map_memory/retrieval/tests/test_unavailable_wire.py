"""Exercise a snapshot read through the host, JSON socket and real WorkerRetrieval reader."""
from pathlib import Path
from contextlib import closing
from types import SimpleNamespace as NS
from threading import Thread
import socket
import pytest
import numpy as np
from PIL import Image
from graphAdapter.map_memory.worker import MemoryWorkerClient,receive,send
from graphAdapter.map_memory.storage.store import load_episode
from graphAdapter.map_memory.retrieval.session import WorkerRetrieval
from graphAdapter.map_memory.retrieval.protocol import sample_native_rgb
from graphAdapter.map_memory.retrieval.host_decision import HostInjection
from graphAdapter.map_memory.retrieval.tests.test_session import recorded,capture,EP,Encoder,VOCAB
def probe(tmp,budget):
    root,ids=recorded(tmp);root=root.resolve()
    uid=capture(1)['frame_uid'];current=capture(5)['frame_uid']
    with closing(load_episode(root,revision=ids[0]))as reader:
        ref=reader.get_view(uid,include_images=False,include_depth=False)['raw_rgb_ref']
    blob=root/ref['path'];payload=blob.read_bytes()
    worker=WorkerRetrieval(Path.cwd());worker.encoder=Encoder();worker.encoder.close=lambda:None;worker.vocabulary=VOCAB
    profile=dict(stage='002',execution_mode='live',async_admission=True,pose_provider='simulator_ground_truth',
                 pose_input_mode='provider_pose',retrieval=dict(enabled=True,mode='uniform_original'))
    options=dict(mode='uniform_original',feature_cache_bytes=64*1024,evidence_policy='ranked')
    packet=dict(episode_uid=EP,capture_seq=5,pose_provider='simulator_ground_truth',pose_record={'episode_instance':'session'})
    svc=NS(frames={current:packet},prepared=None,pointer={'snapshot_id':ids[1]})
    client=MemoryWorkerClient.__new__(MemoryWorkerClient);client.profile=profile;client.active_episode=EP
    client.channel,peer=socket.socketpair()
    errors=[]
    def server():
        try:
            for _ in range(3):
                msg=receive(peer)
                try:
                    reply=worker.read(msg['request'],options=options,service=svc,store=NS(root=root,episode_uid=EP),
                        models=object(),model_identity={},prepared=None)
                    send(peer,dict(status='ok',result=reply))
                except Exception as err:
                    send(peer,dict(status='error',error_type=type(err).__name__,error=str(err)))
        except BaseException as error:errors.append(error)
        finally:worker.close();peer.close()
    thread=Thread(target=server);thread.start()
    events=[];count=0
    def decision():
        nonlocal count
        count+=1
        return dict(event_seq=100+count,frame_uid=current,decision_id=count,env_step=4)
    class Channel:
        def submit_read(self,req):return req
        def wait_read(self,req,timeout):return client.read_memory(req)
        def status(self):return {'failure':None}
    hook=NS(profile={'map_memory':profile},latest_packet=NS(episode_uid=EP,pose_record={'episode_instance':'session'}),
        memory=NS(active_read_root=root),memory_stream=NS(channel=Channel()),coordinator=NS(decision=decision,
        emit=lambda typ,**kwargs:events.append(dict(kind=typ,**kwargs))),
        prepare_memory_read=lambda **kwargs:dict(episode_uid=EP,current_frame_uid=current,current_capture_seq=5,
            snapshot_id=ids[0],cutoff={'capture_seq':4,'event_seq':40},versions={'pose_map_version':0},fresh_enough=True))
    imgs=[Image.fromarray(np.full((8,8,3),i,np.uint8)) for i in range(1,6)]
    def sampler(images,num_frames,width=512,height=512):return sample_native_rgb(images,num_frames,width,height)
    out=[]
    try:
        for label in ['missing','corrupt','restored']:
            if label=='missing':blob.unlink()
            elif label=='corrupt':blob.write_bytes(bytes([payload[0]^1])+payload[1:])
            else:blob.write_bytes(payload)
            begin=len(events)
            try:
                api=HostInjection.begin(hook,instruction='Follow the room.',reasoning=None,reasoning_event=None,host_images=imgs,budget=budget,sampler=sampler)
                if api.decision.history is None:
                    assert api.compile('native question',str,None,None,None)=='native question'
                else:assert api.decision.history.snapshot_id==ids[0]
                assert len(api.images)==budget
                assert all(np.array_equal(np.asarray(a),np.asarray(b)) for a,b in zip(api.images,sampler(imgs,budget)))
                outcome=api.decision.fallback or 'materialized'
            except Exception as err:outcome=type(err).__name__+': '+str(err)
            out.append(dict(fault=label,outcome=outcome,events=[(v['kind'],v.get('reason'),v.get('error_type'),v.get('elapsed_seconds'))for v in events[begin:]]))
    finally:
        client.channel.close();thread.join(4)
        assert not thread.is_alive() and not errors
    return out

@pytest.mark.parametrize('budget',[3,8])
def test_read_faults_are_bound_and_the_same_rpc_channel_recovers(tmp_path,budget):
    missing,corrupt,restored=probe(tmp_path,budget)
    assert missing['outcome']=='missing_material'
    assert [e[0] for e in missing['events']]==['MemoryReadRequested','MemoryReadFallback']
    assert missing['events'][-1][3]>=0
    assert corrupt['events'][-1][0]=='MemoryReadRejected' and corrupt['events'][-1][2]=='IntegrityError'
    assert 'checksum' in corrupt['outcome'] and all(e[0]!='MemoryMaterialized'for e in corrupt['events'])
    assert restored['outcome']=='materialized' and restored['events'][-1][0]=='MemoryMaterialized'


def test_missing_file_is_distinct_from_escape_and_undecodable_pixels(tmp_path):
    from graphAdapter.map_memory.storage.pages import FactMaterializer
    from graphAdapter.map_memory.storage.archive import IntegrityError,UnavailableMaterial,digest
    data=b'not a valid raster image'
    ref=dict(path='image.png',bytes=len(data),sha256=digest(data))
    reader=FactMaterializer(tmp_path,{})
    try:
        with pytest.raises(UnavailableMaterial,match='missing_material'):reader.image(ref)
        (tmp_path/'image.png').write_bytes(data)
        with pytest.raises(UnavailableMaterial,match='undecodable_image'):reader.image(ref)
        (tmp_path/'image.png').write_bytes(bytes([data[0]^1])+data[1:])
        with pytest.raises(IntegrityError,match='checksum') as mismatch:reader.image(ref)
        assert not isinstance(mismatch.value,UnavailableMaterial)
        with pytest.raises(IntegrityError,match='outside') as escape:reader.image(dict(ref,path='../absent.png'))
        assert not isinstance(escape.value,UnavailableMaterial)
    finally:reader.close()


def test_depth_codec_unavailability_is_limited_to_decode_errors(tmp_path):
    from graphAdapter.map_memory.storage.pages import FactMaterializer
    from graphAdapter.map_memory.storage.archive import UnavailableMaterial,digest
    from unittest.mock import patch
    reader=FactMaterializer(tmp_path,{})
    data=b'bad depth payload'
    (tmp_path/'depth.npz').write_bytes(data)
    uid='e:f1';ref=dict(path='depth.npz',bytes=len(data),sha256=digest(data))
    reader.facts={uid:dict(rgb=None,host_view=None,depth=ref)}
    try:
        with patch.object(reader,'capture',return_value={'arrays':{}}):
            with pytest.raises(UnavailableMaterial,match='undecodable_depth'):
                reader.view(uid,{},'pin',images=False,depth=True)
    finally:reader.close()
