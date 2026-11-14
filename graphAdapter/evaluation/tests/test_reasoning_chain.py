import pytest
from graphAdapter.evaluation import reasoning_chain as audit

def fixture():
    ident=dict(episode_uid="ep",frame_uid="f",env_step=4)
    dec=dict(ident,kind="decision",decision_id=5,event_seq=20)
    tied=dict(ident,decision_id=5,call_id=5,request_id="req",snapshot_id="pin")
    flow=[dec,dict(tied,kind="HostInputAudit",event_seq=22),
          dict(tied,kind="MemoryGenerateReturned",event_seq=23),
          dict(ident,kind="MemoryReasoningAvailable",event_seq=24,decision_id=5,call_id=5),
          dict(ident,kind="decision",event_seq=25,decision_id=6)]
    tr=[dict(kind="model_call",call_id=5,frame=4,prompt="first",normalized_output="<BEGIN_OF_REASONING> check the couch"),
        dict(kind="model_call",call_id=6,frame=4,prompt='The reasoning from 0 steps ago was: "check the couch". Act.',
             normalized_output="<BEGIN_OF_ACTION> The next action is turn right 45 degree."),
        dict(kind="primitive_action",last_call_id=6,step=5,action=3,done=False,stop_source=None)]
    return tr,flow

def test_material_can_act_via_next_native_call(monkeypatch):
    monkeypatch.setattr(audit,'_question_builder',lambda:(None,lambda s:s.split('> ',1)[1]))
    tr,f=fixture()
    chain,=audit.audit_material_chains(tr,f)
    assert chain['first_mode']=='reason' and chain['same_frame_followup_calls']==[6]
    assert chain['followups_with_memory']==[] and chain['first_primitive']['action']==3
    assert audit.audit_material_chains(tr[:-1],f)[0]['first_primitive'] is None
    tr[2].update(action=0,done=True,stop_source='reason_stuck',last_call_id=5)
    chain,=audit.audit_material_chains([tr[0],tr[2]],f[:-1])
    assert chain['first_primitive']['stop_source']=='reason_stuck'

@pytest.mark.parametrize('part,index,field,value',[
    ('trace',1,'prompt','wrong text'),('trace',1,'frame',5),('trace',2,'last_call_id',5),('trace',2,'action',2),
    ('flow',2,'snapshot_id','wrong'),('flow',3,'frame_uid','next'),('flow',3,'event_seq',26)])
def test_reject_crossed_reasoning_or_action(monkeypatch,part,index,field,value):
    monkeypatch.setattr(audit,'_question_builder',lambda:(None,lambda s:s.split('> ',1)[1]))
    tr,f=fixture();(tr if part=='trace' else f)[index][field]=value
    with pytest.raises(ValueError):audit.audit_material_chains(tr,f)
