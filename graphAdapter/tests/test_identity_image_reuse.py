import numpy as np
import pytest
from PIL import Image
from graphAdapter.map_memory.storage.store import EpisodeStore,IntegrityError
from graphAdapter.map_memory.tests.test_storage import EP,capture,arrays

def test_identity_view_encodes_once_and_keeps_identical_references(tmp_path,monkeypatch):
    store=EpisodeStore(tmp_path/'map',EP,dataset='r2r');calls=[];original=Image.Image.save
    def save(self,*a,**k):calls.append(1);return original(self,*a,**k)
    monkeypatch.setattr(Image.Image,'save',save)
    try:
        rgb,raw,aligned,mask=arrays();rgb[:]=127
        record=store.archive_frame(capture(1),rgb,raw,aligned,mask,host_view=rgb.copy(),host_transform={'kind':'identity'})
        assert len(calls)==1 and record['files']['host_view']==record['files']['rgb']
        assert np.array_equal(store.read_rgb(record['frame_uid'],host=True),rgb)
    finally:store.close()


def test_false_identity_is_rejected_and_nonidentity_keeps_original_behavior(tmp_path):
    store=EpisodeStore(tmp_path/'map',EP,dataset='r2r')
    try:
        rgb,raw,aligned,mask=arrays();host=rgb.copy();host[0,0]=255
        with pytest.raises(IntegrityError,match='Identity host transform'):
            store.archive_frame(capture(1),rgb,raw,aligned,mask,host_view=host,host_transform={'kind':'identity'})
        record=store.archive_frame(capture(1),rgb,raw,aligned,mask,host_view=host,host_transform={'kind':'test_transform'})
        assert record['files']['host_view']!=record['files']['rgb']
        assert np.array_equal(store.read_rgb(record['frame_uid'],host=True),host)
    finally:store.close()
