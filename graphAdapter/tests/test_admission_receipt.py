import copy
import pytest
from graphAdapter.map_memory.admission_receipt import validated_completion


def source():return dict(episode_uid='episode',frame_uid='episode:f1',capture_seq=1,event_seq=10)
def receipt():return dict(frame_uid='episode:f1',source_packet_event_seq=10,snapshot_id='a'*64,cutoff=dict(capture_seq=1,event_seq=10),versions=dict(pose_map_version=0))


def test_real_commit_shape_is_copied_and_visual_only_revision_allowed():
    value=receipt();got=validated_completion(source(),value)
    value['cutoff']['event_seq']=999
    assert got['cutoff']['event_seq']==10
    value=receipt();value['versions']['pose_map_version']=None
    assert validated_completion(source(),value)['versions']['pose_map_version'] is None


@pytest.mark.parametrize('kind',['enqueue_only','frame','source_event','capture_cutoff','event_cutoff','version','snapshot','duplicate'])
def test_wrong_or_uncommitted_completion_never_becomes_publication(kind):
    value=receipt()
    if kind=='enqueue_only':value={'accepted':True,'frame_uid':'episode:f1'}
    elif kind=='frame':value['frame_uid']='episode:f2'
    elif kind=='source_event':value['source_packet_event_seq']=20
    elif kind=='capture_cutoff':value['cutoff']['capture_seq']=2
    elif kind=='event_cutoff':value['cutoff']['event_seq']=20
    elif kind=='version':value['versions']['pose_map_version']=True
    elif kind=='snapshot':value['snapshot_id']='queued'
    else:value['duplicate']=True
    with pytest.raises(ValueError):validated_completion(source(),value)


def test_measurement_cannot_lose_version_and_episode_echo_cannot_conflict():
    packet=source();packet['pose_record']={'geometry_status':'available'}
    value=receipt();value['versions']['pose_map_version']=None
    with pytest.raises(ValueError,match='revision'):validated_completion(packet,value)
    value=receipt();value['episode_uid']='different'
    with pytest.raises(ValueError,match='episode'):validated_completion(source(),value)
    packet=source();packet['event_seq']=1
    value=receipt();value['source_packet_event_seq']=True;value['cutoff']['event_seq']=1
    with pytest.raises(ValueError,match='observation'):validated_completion(packet,value)
