import numpy as np
import pytest
from graphAdapter.map_memory.storage.store import EpisodeStore,load_episode,canonical,digest,IntegrityError
from graphAdapter.map_memory.tests.test_storage import EP,archive,graph,capture


def recorded(tmp_path, *, alter_record=None, alter_arrays=None, second_revision=False):
    writer=EpisodeStore(tmp_path/'map',EP,dataset='r2r');raw=archive(writer,1);uid=capture(1)['frame_uid']
    identity={'weights':{'clip':'frozen-test'},'preprocess_hash':'p','vocabulary_sha256':'v'}
    arrays=dict(xyxy=np.array([[1,1,4,4]],np.float32),mask=np.ones((1,8,8),bool),confidence=np.array([.8],np.float32),class_id=np.array([3]),image_feats=np.array([[0.,1.,0.]],np.float32),full_clip=np.array([1.,0.,0.],np.float32),local_points=np.zeros((1,3),np.float32))
    if alter_arrays is not None:alter_arrays(arrays)
    record=writer.save_detections(uid,arrays,dict(count=1,image_hw=[8,8],has_full_clip=True,raw_signature=raw['raw_signature'],model_identity_hash=digest(canonical(identity))))
    if alter_record is not None:alter_record(record)
    g=graph([1]);g['model_identity']=identity;g['views'][uid]['detection_record']=record
    writer.publish(g,{'pose_map_version':0},{'capture_seq':1,'event_seq':10})
    if second_revision:
        g['review_marker']='second revision with unchanged features'
        writer.publish(g,{'pose_map_version':0},{'capture_seq':1,'event_seq':10})
    writer.close()
    return tmp_path/'map',uid


def test_features_use_existing_payload_without_decoding_masks_or_points(tmp_path,monkeypatch):
    root,uid=recorded(tmp_path);reader=load_episode(root)
    original=np.lib.npyio.NpzFile.__getitem__
    def only_features(self,name):
        if name in ('mask','local_points'):raise AssertionError('Retrieval decoded mapping arrays')
        return original(self,name)
    monkeypatch.setattr(np.lib.npyio.NpzFile,'__getitem__',only_features)
    try:
        features=reader.get_view_features(uid)
        np.testing.assert_array_equal(features['full_clip'],[1,0,0])
        assert features['frame_uid']==uid and features['snapshot_id']==reader.snapshot_id
        assert features['class_ids'].tolist()==[3]
        with pytest.raises(ValueError):features['full_clip'].setflags(write=True)
    finally:reader.close()


def test_feature_read_detects_changed_payload(tmp_path):
    root,uid=recorded(tmp_path);reader=load_episode(root)
    try:
        reference=reader.get_view_feature_reference(uid)
        (root/reference['source_ref']['path']).write_bytes(b'broken')
        with pytest.raises(IntegrityError):reader.get_view_features(uid)
    finally:reader.close()


def test_shared_cache_reuses_arrays_across_revisions_and_preserves_snapshot(tmp_path):
    from graphAdapter.map_memory.storage.features import EpisodeFeatureCache
    root,uid=recorded(tmp_path,second_revision=True)
    cache=EpisodeFeatureCache(root)
    current=load_episode(root,feature_cache=cache)
    parent=current.pages.parent
    old=load_episode(root,revision=parent,feature_cache=cache)
    try:
        first=old.get_view_features(uid);hashed=cache.verifier.bytes_read
        second=current.get_view_features(uid)
        assert first['snapshot_id']==parent and second['snapshot_id']==current.snapshot_id
        assert first['snapshot_id']!=second['snapshot_id']
        assert cache.decodes==1 and cache.hits==1 and cache.verifier.bytes_read==hashed
        np.testing.assert_array_equal(first['full_clip'],second['full_clip'])
        assert cache.bytes<=cache.max_bytes
        old.close()
        current.get_view_features(uid)
        assert not cache.closed
    finally:
        old.close();current.close();cache.close()
    assert cache.bytes==0 and cache.closed


def test_cache_cannot_cross_episode_roots(tmp_path):
    from graphAdapter.map_memory.storage.features import EpisodeFeatureCache
    root,uid=recorded(tmp_path/'first')
    other,_=recorded(tmp_path/'other')
    cache=EpisodeFeatureCache(root)
    with pytest.raises(IntegrityError):load_episode(other,feature_cache=cache)
    cache.close()
    with pytest.raises(IntegrityError):load_episode(root,feature_cache=cache)


def test_cached_payload_still_rejects_same_size_corruption(tmp_path):
    root,uid=recorded(tmp_path);reader=load_episode(root)
    try:
        features=reader.get_view_features(uid)
        path=root/features['source_ref']['path']
        data=bytearray(path.read_bytes());data[len(data)//2]^=1;path.write_bytes(data)
        with pytest.raises(IntegrityError):reader.get_view_features(uid)
    finally:reader.close()


@pytest.mark.parametrize('field,value',[('raw_signature','wrong-frame'),('model_identity_hash','wrong-model')])
def test_feature_provenance_mismatch_rejected(tmp_path,field,value):
    root,uid=recorded(tmp_path,alter_record=lambda row:row['metadata'].update({field:value}))
    reader=load_episode(root)
    try:
        with pytest.raises(IntegrityError):reader.get_view_features(uid)
    finally:reader.close()


@pytest.mark.parametrize('field,value',[
    ('full_clip',np.array([np.nan,0,0],np.float32)),
    ('full_clip',np.zeros(3,np.float32)),
    ('image_feats',np.ones((1,4),np.float32)),
    ('confidence',np.array([2],np.float32)),
    ('class_id',np.array([-1])),
])
def test_invalid_features_are_not_model_evidence(tmp_path,field,value):
    root,uid=recorded(tmp_path,alter_arrays=lambda arrays:arrays.update({field:value}))
    reader=load_episode(root)
    try:
        with pytest.raises(IntegrityError):reader.get_view_features(uid)
    finally:reader.close()


def test_unknown_view_is_not_silently_replaced(tmp_path):
    root,_=recorded(tmp_path);reader=load_episode(root)
    try:
        with pytest.raises(KeyError):reader.get_view_features('another-episode:f000001')
    finally:reader.close()


def test_zero_cache_budget_does_not_retain_arrays(tmp_path):
    from graphAdapter.map_memory.storage.features import EpisodeFeatureCache
    root,uid=recorded(tmp_path);cache=EpisodeFeatureCache(root,max_bytes=0)
    reader=load_episode(root,feature_cache=cache)
    try:
        reader.get_view_features(uid);reader.get_view_features(uid)
        assert cache.decodes==2 and cache.bytes==0 and not cache.items
    finally:reader.close();cache.close()


def test_cached_feature_arrays_are_not_copied_per_query(tmp_path):
    root,uid=recorded(tmp_path);reader=load_episode(root)
    try:
        first=reader.get_view_features(uid);second=reader.get_view_features(uid)
        for field in ('full_clip','object_clip','class_ids','confidence'):
            assert first[field] is second[field]
            with pytest.raises(ValueError):second[field].setflags(write=True)
    finally:reader.close()



def test_class_only_read_promotes_without_redecoding_and_binds_revision(tmp_path,monkeypatch):
    from graphAdapter.map_memory.storage import features
    root,uid=recorded(tmp_path,second_revision=True)
    cache=features.EpisodeFeatureCache(root)
    current=load_episode(root,feature_cache=cache);old=load_episode(root,revision=current.pages.parent,feature_cache=cache)
    decoded=[];original=features.decode_feature_arrays
    def track(path,expected,names,**options):
        decoded.extend(names)
        return original(path,expected,names,**options)
    monkeypatch.setattr(features,"decode_feature_arrays",track)
    try:
        one=old.get_view_class_ids(uid)
        two=current.get_view_class_ids(uid)
        assert decoded==["class_id"] and one["snapshot_id"]!=two["snapshot_id"]
        all_fields=current.get_view_features(uid)
        assert decoded.count("class_id")==1 and "image_feats" in decoded and len(cache.items)==1
        assert old.get_view_class_ids(uid)["class_ids"] is all_fields["class_ids"]
        assert cache.bytes<=cache.max_bytes
        ref=one["source_ref"];path=root/ref["path"];bad=bytearray(path.read_bytes());bad[-1]^=1;path.write_bytes(bad)
        with pytest.raises(IntegrityError):old.get_view_class_ids(uid)
    finally:old.close();current.close();cache.close()



def test_repeat_boxes_do_not_read_embeddings_or_masks_and_are_immutable(tmp_path,monkeypatch):
    from graphAdapter.map_memory.storage import features
    root,uid=recorded(tmp_path)
    reader=load_episode(root)
    observed=[];original=features.decode_feature_arrays
    def track(path,expected,names,**options):
        observed.extend(names)
        return original(path,expected,names,**options)
    monkeypatch.setattr(features,"decode_feature_arrays",track)
    try:
        for _ in range(2):
            data=reader.get_view_class_ids(uid,include_boxes=True)
            assert data["xyxy"].tolist()==[[1,1,4,4]]
        assert observed==["class_id","xyxy"]
        with pytest.raises(ValueError):data["xyxy"].setflags(write=True)
    finally:reader.close()

def test_class_confidence_box_and_full_read_share_same_arrays(tmp_path,monkeypatch):
    from graphAdapter.map_memory.storage import features
    root,uid=recorded(tmp_path,second_revision=True)
    cache=features.EpisodeFeatureCache(root)
    new=load_episode(root,feature_cache=cache)
    old=load_episode(root,revision=new.pages.parent,feature_cache=cache)
    decoded=[]
    original=features.decode_feature_arrays
    def track(path,expected,names,**kwargs):
        decoded.extend(names)
        return original(path,expected,names,**kwargs)
    monkeypatch.setattr(features,'decode_feature_arrays',track)
    try:
        score=old.get_view_class_ids(uid,include_confidence=True)
        box=new.get_view_class_ids(uid,include_boxes=True)
        assert score['snapshot_id']!=box['snapshot_id']
        assert decoded==['class_id','confidence','xyxy']
        full=new.get_view_features(uid)
        assert full['class_ids'] is score['class_ids'] is box['class_ids']
        assert full['confidence'] is score['confidence']
        assert decoded==['class_id','confidence','xyxy','image_feats','full_clip']
        assert len(cache.items)==1 and cache.bytes==sum(a.nbytes for a in cache.items[next(iter(cache.items))][0].values())
        target=root/score['source_ref']['path']
        raw=bytearray(target.read_bytes());raw[-1]^=1;target.write_bytes(raw)
        with pytest.raises(IntegrityError):new.get_view_class_ids(uid,include_confidence=True)
    finally:old.close();new.close();cache.close()
    assert not cache.items and cache.bytes==0


def test_score_only_rejects_bad_confidence_and_keeps_prior_cache_on_oversize(tmp_path):
    from graphAdapter.map_memory.storage.features import EpisodeFeatureCache
    root,uid=recorded(tmp_path/'bad',alter_arrays=lambda a:a.update(confidence=np.array([float('nan')],np.float32)))
    rd=load_episode(root)
    try:
        rd.get_view_class_ids(uid)
        with pytest.raises(IntegrityError):rd.get_view_class_ids(uid,include_confidence=True)
    finally:rd.close()
    root,uid=recorded(tmp_path/'small')
    cache=EpisodeFeatureCache(root,max_bytes=12)
    rd=load_episode(root,feature_cache=cache)
    try:
        scores=rd.get_view_class_ids(uid,include_confidence=True)
        rd.get_view_features(uid)
        assert rd.get_view_class_ids(uid,include_confidence=True)['class_ids'] is scores['class_ids']
        assert cache.peak_bytes==cache.bytes==12
    finally:rd.close();cache.close()
