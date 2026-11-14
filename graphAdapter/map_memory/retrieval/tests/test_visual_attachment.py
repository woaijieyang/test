from dataclasses import replace
from types import SimpleNamespace
import numpy as np
import pytest
from graphAdapter.map_memory.retrieval.protocol import retrieval_settings
from graphAdapter.map_memory.retrieval.evidence import ExtraRecord
from graphAdapter.map_memory.retrieval.host_input_compiler import make_attachment,VisualInputs,attachment_suffix
from graphAdapter.map_memory.retrieval.host_input_compiler import ImageSlot,PreparedHistory
from graphAdapter.map_memory.retrieval.tests.test_session import recorded,VOCAB,Encoder,request,capture,EP
from graphAdapter.map_memory.storage.store import load_episode,IntegrityError
from graphAdapter.map_memory.retrieval.session import MemoryRetrievalSession

def test_pinned_supplement_is_distinct_from_native_observations(tmp_path):
    root,ids=recorded(tmp_path);session=MemoryRetrievalSession(root,EP,'session',Encoder(),VOCAB,evidence_policy='landmark_attachment')
    req=request(ids,mode='native_plus_attachment');req['budget']=3
    reader=load_episode(root,revision=ids[0])
    try:
        response=session.read(req,current_snapshot_id=ids[1])
        assert response['selection'] is None and response['additional_evidence']
        from graphAdapter.map_memory.retrieval.evidence import resolve
        record=resolve(response['additional_evidence'],reader,VOCAB,5,req['query']['instruction'])[0]
        slot=ImageSlot(3,capture(5)['frame_uid'],4,5,'live',(),None,None,None,None,'x',True,ids[1])
        native=PreparedHistory((None,None,None),(replace(slot,index=1,is_current=False),replace(slot,index=2,is_current=False),slot),reader.snapshot_id,3)
        attachment=make_attachment(native,reader,record)
        from graphAdapter.map_memory.retrieval.host_input_compiler import from_source
        card=from_source(attachment,reader,native,req['query']['instruction'],VOCAB)
        fields=card.fields()
        assert fields['instruction_landmark']=='door' and fields['current_image_slot']==3 and fields['historical_photo_slot']==4
        assert fields['observed_step']<fields['current_step'] and fields['detector_region_xyxy_pixels']==[1,1,4,4]
        assert card.suffix().count('<image>')==1 and ':d'not in card.suffix()
        with pytest.raises(IntegrityError):from_source(attachment,reader,native,'Go to a chair.',VOCAB)
        merged=VisualInputs(native,attachment)
        assert merged.slots[:3]==native.slots and merged.slots[2].is_current and not merged.slots[3].is_current
        assert merged.slots[3].source_snapshot_id==reader.snapshot_id and merged.slots[3].evidence_group==record.source_refs
        assert len(merged.images)==4 and merged.budget==4
        assert make_attachment(replace(native,slots=(replace(slot,frame_uid=attachment.slot.frame_uid),slot)),reader,record)is None
        with pytest.raises(IntegrityError):make_attachment(replace(native,snapshot_id='wrong'),reader,record)
        with pytest.raises(IntegrityError):make_attachment(native,reader,replace(record,steps=(50,)))
    finally:reader.close();session.close()

def test_attachment_is_explicit_and_cannot_add_arbitrary_placeholders():
    p=dict(stage='002',execution_mode='live',async_admission=True,pose_input_mode='provider_pose',pose_provider='simulator_ground_truth',
           retrieval=dict(enabled=True,mode='native_plus_attachment',evidence_policy='landmark_attachment'))
    assert retrieval_settings(p)['mode']=='native_plus_attachment'
    guarded=dict(p['retrieval'],evidence_policy='dynamic_evo_context',landmark_query='current_plan',
                 landmark_ambiguity='omit_competing_instances')
    assert retrieval_settings(dict(p,retrieval=guarded))['landmark_ambiguity']=='omit_competing_instances'
    for invalid in [dict(guarded,landmark_query=None),dict(guarded,landmark_ambiguity='pick_last')]:
        with pytest.raises(ValueError):retrieval_settings(dict(p,retrieval=invalid))

    with pytest.raises(ValueError):retrieval_settings(dict(p,retrieval=dict(p['retrieval'],mode='facts_only')))
    with pytest.raises(IntegrityError):attachment_suffix(1,'untrusted <image>',with_image=True)

