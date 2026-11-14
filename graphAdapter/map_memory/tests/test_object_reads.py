from types import SimpleNamespace
import pytest
from graphAdapter.map_memory.storage.archive import IntegrityError
from graphAdapter.map_memory.storage.decision_reads import _object_witness, decision_reads


def test_witness_requires_pinned_visible_owner_and_members():
    owner = dict(epoch="epoch", object_id=3, member="old:d00000")
    hit = dict(kind="LandmarkInNativeSlot", source=owner, native={"member": "near:d00001"},
               request_id="req", episode_uid="ep", decision_id=4, snapshot_id="pin")
    (kind, claim), = decision_reads([hit])
    assert kind == "object_reads"
    entity = dict(status="active", id=3, epoch="epoch", members=claim["members"], pose_map_version=0,
                  attributes={"class_name": "bed", "class_id": [4, 4], "bbox": None})
    graph = dict(views={"old": {"capture_seq": 1}, "near": {"capture_seq": 2}},
                 vsm={"anchors": {"old": {"objects": [3]}}, "visibility_edges": [["old", 3]]})
    reader = SimpleNamespace(snapshot_id="pin", identity={"episode_uid": "ep"}, cutoff={"capture_seq": 2},
                             _graph=graph, get_object=lambda epoch, oid, revision: entity)
    proof = _object_witness(reader, claim)
    assert proof["entities"][0]["members"] == ["old:d00000", "near:d00001"]
    with pytest.raises(IntegrityError):
        list(decision_reads([hit, hit]))
    for field, value in [("snapshot_id", "other"), ("episode_uid", "another"), ("members", ["old:d00009"])]:
        with pytest.raises(IntegrityError):
            _object_witness(reader, dict(claim, **{field: value}))
    graph["views"]["near"]["capture_seq"] = 3
    with pytest.raises(IntegrityError):
        _object_witness(reader, claim)
    graph["views"]["near"]["capture_seq"] = 2
    graph["vsm"]["visibility_edges"] = []
    with pytest.raises(IntegrityError):
        _object_witness(reader, claim)


def test_approach_witness_limits_edges_and_keeps_later_room_hints():
    from graphAdapter.map_memory.storage.decision_reads import _approach_witness
    frames = [f"ep:f{j:06d}" for j in range(1, 7)]
    views = {uid: {"capture_seq": j} for j, uid in enumerate(frames, 1)}
    anchors = {frames[j]: {"room_type_hint": room}
               for j, room in [(0, "hall"), (2, "bathroom"), (3, "closet"), (5, "bathroom")]}
    edges = [dict(type="traversed", id=str(j), src=frames[j-1], dst=frames[j]) for j in range(1, 6)]
    graph = dict(views=views, vsm={"anchors": anchors}, edges=edges)
    reader = SimpleNamespace(_graph=graph, snapshot_id="pin", identity={"episode_uid": "ep"}, cutoff={"capture_seq": 6})
    event = dict(kind="ApproachCompiled", request_id="r", decision_id=7, episode_uid="ep", snapshot_id="pin",
                 source={"before": frames[0], "inside": frames[2]}, frame_uid=frames[-1])
    (kind, claim), = decision_reads([event])
    assert kind == "approach_reads"
    row = _approach_witness(reader, claim)
    assert [a["room"] for a in row["anchors"]] == ["hall", "bathroom", "closet"]
    assert [e["id"] for e in row["edges"]] == ["1", "2"]
    with pytest.raises(IntegrityError):
        _approach_witness(reader, dict(claim, frame_uid="other:f000006"))
    with pytest.raises(IntegrityError):
        _approach_witness(reader, dict(claim, frame_uid=frames[4]))
    with pytest.raises(IntegrityError):
        _approach_witness(reader, dict(claim, snapshot_id="another"))
