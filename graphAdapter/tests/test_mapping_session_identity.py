import threading
from dataclasses import FrozenInstanceError
import pytest
from poseAdapter import PoseAdapter
from poseAdapter.interfaces.mapping import MappingSessionIdentity


def test_identity_available_without_pose_and_frozen_across_reset():
    # Explicit unit fixture: the getter must not access buffers or a backend.
    adapter=PoseAdapter.__new__(PoseAdapter)
    adapter._publication_lock=threading.RLock();adapter._active=lambda:None
    adapter.episode_id='episode';adapter._episode_instance='generation-a'
    before=adapter.get_mapping_session_identity()
    assert before.to_record()==dict(episode_id='episode',episode_instance='generation-a')
    with pytest.raises(FrozenInstanceError):before.episode_instance='changed'
    adapter._episode_instance='generation-b'
    assert adapter.get_mapping_session_identity().episode_instance=='generation-b'
    assert before.episode_instance=='generation-a'


def test_inactive_session_is_rejected_before_identity_read():
    adapter=PoseAdapter.__new__(PoseAdapter);adapter._publication_lock=threading.RLock()
    def inactive():raise RuntimeError('not active')
    adapter._active=inactive
    with pytest.raises(RuntimeError,match='not active'):adapter.get_mapping_session_identity()
    with pytest.raises(ValueError):MappingSessionIdentity('episode','')
