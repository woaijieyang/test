import pytest
from graphAdapter.map_memory.worker import MemoryWorkerClient,validate_mapping_profile
from graphAdapter.interfaces.retrieval import retrieval_settings


def options():return {'stage':'002','execution_mode':'live','async_admission':True,'pose_provider':'simulator_ground_truth','pose_input_mode':'provider_pose',
    'retrieval':{'enabled':True,'mode':'graph_image_only'}}

def request():return {'protocol_version':1,'request_id':'r','episode_instance':'s','mode':'graph_image_only','budget':8,
    'query':{'episode_uid':'ep','snapshot_id':'a'*64,'current_frame_uid':'f1','current_capture_seq':1,
             'cutoff_capture_seq':1,'cutoff_event_seq':10,'instruction':'Go ahead.'}}

def test_disabled_001_read_is_not_implicitly_enabled():
    assert retrieval_settings({'stage':'001'})is None
    with pytest.raises(ValueError):retrieval_settings(dict(options(),stage='001'))
    with pytest.raises(ValueError):retrieval_settings(dict(options(),execution_mode='archive_only'))
    with pytest.raises(ValueError):retrieval_settings(dict(options(),async_admission=False))


def test_client_serialized_read_checks_profile_and_response_binding():
    client=MemoryWorkerClient.__new__(MemoryWorkerClient);client.profile=options();client.active_episode='ep'
    calls=[]
    def call(message):
        calls.append(message)
        return {'result':{'request_id':'r','episode_uid':'ep','episode_instance':'s','snapshot_id':'a'*64}}
    client.call=call
    assert client.read_memory(request())['request_id']=='r'
    assert calls[0]['op']=='read_memory'
    wrong=request();wrong['query']['episode_uid']='other'
    with pytest.raises(ValueError):client.read_memory(wrong)
    client.call=lambda message:{'result':{'request_id':'late'}}
    with pytest.raises(ValueError):client.read_memory(request())


def test_profile_is_explicit_and_unsupported_settings_rejected():
    result=retrieval_settings(options())
    assert result['read_timeout_seconds']>0 and result['query_cache_bytes']>0
    bad=options();bad['retrieval']['unexpected']='x'
    with pytest.raises(ValueError):retrieval_settings(bad)
