"""Immutable projection, upstream stable order, and source row/crop counterexamples."""
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from graphAdapter.map_memory.retrieval.contracts import CategoryVocabulary, MemoryQuery
from graphAdapter.map_memory.retrieval.evo_material import _source_crop, read_evo_material, topology_projection
from graphAdapter.map_memory.storage.archive import IntegrityError
from graphAdapter.map_memory.storage.store import load_episode


ROOT = Path("/data/zy/vln/case2")
MAP = ROOT / "outputs/graph_memory/candidate_detached_correction001-20261113/review/seal-profile/real-long-prefix/map"
PINS = [
    ("8615bc229e7d341c6583a10ff016e71bc6942be7049e4eb7147ab286e863e370", 14),
    ("48e22244a6f160d8df78a52f224ed2b5fc835c05c6feaada87ec98c470243939", 22),
]


@pytest.mark.parametrize("pin,expected_step", PINS)
def test_real_pin_author_order_without_hints_and_source_identity(pin, expected_step, monkeypatch):
    vocabulary = CategoryVocabulary.from_file(ROOT / "vendor_sources/EvoMemNav/data/scannet200_classes.txt")
    with closing(load_episode(MAP, revision=pin)) as reader:
        def no_pixels(*args, **kwargs):
            pytest.fail("Metadata adapter decoded image pixels")

        monkeypatch.setattr(reader, "get_view", no_pixels)
        monkeypatch.setattr(reader.materializer, "image", no_pixels)
        projection = topology_projection(reader)
        uid = projection["views"][-1]
        cutoff = reader.cutoff
        query = MemoryQuery(reader.identity["episode_uid"], pin, uid, cutoff["capture_seq"],
                            cutoff["capture_seq"], cutoff["event_seq"], "continue")
        result = read_evo_material(reader, query, vocabulary)
        assert [a["uid"] for a in result["anchors"]] == [u for u in reversed(projection["anchors_in_order"]) if u != uid][:5]
        assert "Rooms(now)" in result["summary"]
        assert set(projection["detections"]) >= {ref for _, _, ref in projection["members"]}
        entry, = [a for a in result["anchors"] if a["step"] == expected_step]
        crop, = [c for c in entry["evidence"] if c["object_id"] == 9]
        assert crop["label"] == "column"
        assert crop["member"] in projection["detections"]
        assert [crop["object_epoch"], 9, crop["member"]] in projection["members"]
        assert read_evo_material(reader, query, vocabulary, max_views=0)["anchors"] == []
        assert read_evo_material(reader, query, vocabulary, max_views=1)["anchors"] == result["anchors"][:1]
        with pytest.raises(IntegrityError):
            read_evo_material(reader, replace(query, episode_uid="unrelated"), vocabulary)


def test_first_prompt_row_only_and_unique_member():
    # Two plausible source rows have the same detector class. Row 0 has different pixels.
    source = dict(class_ids=np.array([0, 0]), xyxy=np.array([[0, 0, 2, 2], [1.9, 2.1, 5.8, 6.7]]))
    prompt = dict(obj_id=[7, 7], class_id=[0, 0], xyxy=[[1.9, 2.1, 5.8, 6.7], [0, 0, 2, 2]])
    def select():
        return _source_crop("frame", 7, "epoch", {"class_name":"chair"}, prompt, source,
                            [0, 1], [8, 8], ["sofa chair"])
    crop, reason = select()
    assert reason is None
    assert (crop["prompt_row"], crop["index"], crop["box_xyxy"]) == (0, 1, [1, 2, 5, 6])
    assert (crop["label"], crop["aggregate_label"]) == ("sofa chair", "chair")
    source["xyxy"][0] = source["xyxy"][1]
    assert select() == (None, "ambiguous_camera_row")


def test_crop_lexical_priority_is_not_camera_label_or_confidence():
    from graphAdapter.map_memory.retrieval.evo_material import crop_query_match
    assert crop_query_match('sofa chair',('chair',),('door','sofa'))=={'instruction':['chair'],'reasoning':['sofa']}
    assert crop_query_match('power outlet',('bench','door'),())=={'instruction':[],'reasoning':[]}


def test_query_spans_keep_repeated_mentions_and_original_unicode_offsets():
    from graphAdapter.map_memory.retrieval.evidence import match_category_cues,category_source_spans
    from graphAdapter.evaluation.evo_material_audit import audit_query_sources
    text='Straße: BENCH by the door, then Door on the doorstep.'
    vocab=('bench','door','strasse')
    table=category_source_spans(text,vocab)
    assert tuple(table)==match_category_cues(text,vocab)==vocab
    assert table['bench']==[dict(start=8,end=13,text='BENCH')]
    assert table['strasse']==[dict(start=0,end=6,text='Straße')]
    assert [r['text'] for r in table['door']]==['door','Door']
    both=dict(instruction=table,reasoning={})
    audit_query_sources(both,text,None,vocab)
    with pytest.raises(ValueError):audit_query_sources(both,text,'look at the door',vocab)
    table['door'].pop()
    with pytest.raises(ValueError):audit_query_sources(both,text,None,vocab)
