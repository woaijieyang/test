from types import SimpleNamespace
import pytest
from graphAdapter.map_memory.retrieval.semantic_topology import requested_exit_room, historical_approach
from graphAdapter.map_memory.storage.store import IntegrityError


def test_reasoning_must_request_future_exit():
    request = "Enter the bathroom then go back out of the bathroom."
    assert requested_exit_room(request, "The next plan is to exit the bathroom.") == "bathroom"
    assert requested_exit_room(request, "I completed exiting the bathroom. The next plan is to turn left.") is None
    assert requested_exit_room("Enter the bathroom and stop.", "The next plan is to exit the bathroom.") is None


def test_only_recorded_chain_supports_approach():
    views = {str(n): {"capture_seq":n} for n in range(1,6)}
    anchors = {str(n): {"room_type_hint":room} for n,room in [(1,"closet"),(3,"bedroom"),(4,"bedroom"),(5,"other")]}
    rows = [dict(pre=str(i-1),post=str(i),action=dict(action_id=1,collision=False),
                 motion=dict(traversed=dict(id=str(i),src=str(i-1),dst=str(i)))) for i in [2,3]]
    r = SimpleNamespace(_graph=dict(views=views,vsm=dict(anchors=anchors)),cutoff=dict(capture_seq=5),
                        get_trace=lambda a,b:list(rows))
    assert historical_approach(r,5,"bedroom")["traversed_edges"]==["2","3"]
    assert historical_approach(r,6,"bedroom") is None
    assert historical_approach(r,5,"bedroom")["unverified_forward_steps"]==[]
    rows[1]["motion"]["traversed"]=None
    rows[1]["action"]["collision"]=True
    assert historical_approach(r,5,"bedroom")["unverified_forward_steps"]==[2]
    rows[1]["action"]["action_id"]=2
    assert historical_approach(r,5,"bedroom")["unverified_forward_steps"]==[]
    rows[1]["pre"]="bad"
    with pytest.raises(IntegrityError):historical_approach(r,5,"bedroom")
    rows.pop()
    assert historical_approach(r,5,"bedroom") is None



def test_exit_intent_uses_actual_room_labels_and_affirmative_instruction():
    for phrase in ("exit through the door","exit to the hall","leave the room"):
        assert requested_exit_room(phrase,"The next plan is to "+phrase) is None
    assert requested_exit_room("Do not exit the bathroom.","The next plan is to exit the bathroom.") is None
    assert requested_exit_room("Exit the dining room.","The next plan is to exit the dining room.")=="dining room"


def test_shared_depth_requires_actual_surface_agreement():
    import numpy as np
    from graphAdapter.map_memory.retrieval.semantic_topology import shared_depth_samples
    K=np.array([[4.,0,1.5],[0,4.,1.5],[0,0,1.]])
    a=dict(K=K,pose=np.eye(4),depth=np.ones((4,4)),valid=np.ones((4,4),bool))
    def counts(b):
        return shared_depth_samples(a,b,voxel_size_m=.1,stride=1)
    assert counts(a)['shared_samples']==16
    assert counts(dict(a,depth=np.full((4,4),.5)))['shared_samples']==0
    assert counts(dict(a,valid=np.zeros((4,4),bool)))['comparable_depths']==0
    away=np.diag([-1.,1.,-1.,1.])
    assert counts(dict(a,pose=away))['projected_pixels']==0


def test_region_support_keeps_masks_separate_and_projected_depth_reads_bounded():
    from graphAdapter.map_memory.retrieval.semantic_topology import observed_door_support
    from types import SimpleNamespace
    import numpy as np
    source_uid="one:old";now="one:now"
    class Reader:
        identity={"episode_uid":"one"};versions={"pose_map_version":0}
        _graph={"geometry_state":{"voxel_size":.1}}
        def __init__(self,pin,seq):
            self.snapshot_id=pin;self.cutoff={"capture_seq":seq};self.depth_reads=0
        def get_view(self,uid,include_images,include_depth):
            assert not include_images and include_depth
            self.depth_reads+=1
            z=np.ones((8,8))
            if uid==now:z[:,4:]=2
            return dict(frame_uid=uid,snapshot_id=self.snapshot_id,capture_seq=self.cutoff["capture_seq"],
                        capture=dict(frame_uid=uid,episode_uid="one",K=np.eye(3)),pose_map_version=0,
                        T_G_cv=np.eye(4),depth=dict(aligned_depth=z,valid_mask=np.ones(z.shape,bool)))
        def get_observed_doors(self,uid):
            masks=np.zeros((2,8,8),bool);masks[0,:,:4]=True;masks[1,:,4:]=True
            return dict(frame_uid=uid,snapshot_id=self.snapshot_id,status="available",count=2,image_hw=(8,8),
                        door_mask_bits=np.packbits(masks,axis=2,bitorder="little"),
                        door_proposal_indices=[5,13],door_xyxy=[[0,0,4,8],[4,0,8,8]],door_confidence=[.5,.4])
    old,live=Reader("past",2),Reader("current",3)
    cue=SimpleNamespace(episode_uid="one",frame_uid=now,capture_seq=3,snapshot_id="past",
                        source_snapshot_id="current",pose_map_version=0)
    v=observed_door_support(old,live,source_uid,cue)
    assert [(x["proposal_index"],x["shared_samples"])for x in v["regions"]]==[(5,2),(13,0)]
    assert old.depth_reads==live.depth_reads==1
    cue.source_snapshot_id="wrong"
    with pytest.raises(IntegrityError):observed_door_support(old,live,source_uid,cue)

    cue.source_snapshot_id="current";live.cutoff["capture_seq"]=4
    with pytest.raises(IntegrityError):observed_door_support(old,live,source_uid,cue)

def test_union_uses_original_source_indices_including_occlusions():
    import numpy as np
    from graphAdapter.map_memory.retrieval.semantic_topology import depth_coverage_across_views
    src=dict(depth=np.ones((2,4)),valid=np.ones((2,4),bool),K=np.eye(3),pose=np.eye(4))
    left=src['depth'].copy();left[:,2:]=.4
    right=src['valid'].copy();right[:,:2]=False
    views=[dict(src,depth=left),dict(src,valid=right),dict(src,depth=left)]
    got=depth_coverage_across_views(src,views,voxel_size_m=.1,stride=1)
    assert got['covered_samples']==got['source_samples']==8
    assert [v['shared_samples'] for v in got['views']]==[4,4,4]
    flipped=depth_coverage_across_views(src,[dict(src,pose=np.diag([-1,1,-1,1]))],voxel_size_m=.1,stride=1)
    assert flipped['covered_samples']==flipped['views'][0]['projected_pixels']==0
