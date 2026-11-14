"""Bind positive retrieval metadata even for a pixel-identical reply."""
from types import SimpleNamespace as NS
import pytest
from graphAdapter.map_memory.storage.store import IntegrityError
from graphAdapter.map_memory.retrieval.host_decision import validate_evo_read_header

@pytest.mark.parametrize('field,key,value',[
    ('versions','pose_map_version',True),('versions','pose_map_version',2),
    ('versions','map_version',2),('cutoff','event_seq',False),('cutoff','capture_seq',4)])
def test_evo_positive_reply_binds_typed_publication_header(field,key,value):
    r=NS(identity={'episode_uid':'episode'},snapshot_id='pin',cutoff={'capture_seq':3,'event_seq':8},versions={'pose_map_version':1})
    q=dict(episode_uid='episode',snapshot_id='pin',cutoff_capture_seq=3,cutoff_event_seq=8)
    reply=dict(snapshot_id='pin',cutoff=dict(r.cutoff),versions=dict(r.versions))
    validate_evo_read_header(r,reply,q)
    reply[field][key]=value
    with pytest.raises(IntegrityError):validate_evo_read_header(r,reply,q)
