import json
import pytest
from awarevln_memory.training.artifacts import write_json,digest,identity
from awarevln_memory.training.counterfactual import STATE_FIELDS,preference,label_anchor
from awarevln_memory.training.pipeline import main
from test_data import erow


def branch_fixture(tmp_path,intervention,sr,ndtw=.5,candidate=None):
    body={'anchor_id':'a','reader_sha256':'r','intervention_scope':'current_read_only',
          'continuation_policy_sha256':'c','initial_state':{k:'f'*64 for k in STATE_FIELDS},
          'intervention':intervention,'status':'complete','horizon':'terminal','sr':sr,'spl':.5,'ndtw':ndtw}
    if candidate:body['candidate_id']=candidate
    path=tmp_path/(intervention+str(candidate)+'.json');write_json(path,body)
    return dict(body,evidence_file=str(path),evidence_sha256=digest(path))


def test_set_gain_not_copied_to_each_candidate(tmp_path):
    off=branch_fixture(tmp_path,'OFF',0);on=branch_fixture(tmp_path,'ON',1)
    anchor={'anchor_id':'a','source_split':'train','dataset':'r2r','partition':'train',
            'candidate_ids':['p1','p2','p3'],'continuation_policy_sha256':'c','initial_state':off['initial_state']}
    labelled=label_anchor(anchor,[off,on],'r')
    assert labelled['set_sign']==1 and labelled['utility_sign']==[0,0,0]
    assert labelled['candidate_measured']==[False,False,False]
    single=branch_fixture(tmp_path,'SINGLE',1,candidate='p2')
    labelled=label_anchor(anchor,[off,on,single],'r')
    assert labelled['utility_sign']==[0,1,0]


def test_reject_same_rgb_but_different_hidden_state(tmp_path):
    off=branch_fixture(tmp_path,'OFF',0);on=branch_fixture(tmp_path,'ON',1)
    anchor={'anchor_id':'a','source_split':'train','dataset':'r2r','partition':'train',
            'candidate_ids':['p1','p2','p3'],'continuation_policy_sha256':'c','initial_state':off['initial_state']}
    on['initial_state']=dict(on['initial_state'],torch_rng='e'*64)
    with pytest.raises(ValueError,match='same full state'):label_anchor(anchor,[off,on],'r')


def test_reject_metrics_that_disagree_with_original_evidence(tmp_path):
    off=branch_fixture(tmp_path,'OFF',0);on=branch_fixture(tmp_path,'ON',0);on['sr']=1
    anchor={'anchor_id':'a','source_split':'train','dataset':'r2r','partition':'train',
            'candidate_ids':['p1','p2','p3'],'continuation_policy_sha256':'c','initial_state':off['initial_state']}
    with pytest.raises(ValueError,match='original evidence'):label_anchor(anchor,[off,on],'r')


def test_local_horizon_not_claimed_terminal_sr():
    a=dict(status='complete',horizon='local',sr=1,spl=.5,ndtw=.5)
    with pytest.raises(ValueError):preference(a,a)


def test_cli_budget_and_cumulative_index(tmp_path):
    report=main(['budget','--samples','500','--epochs','4'])
    assert report['max_steps']==125
    annotation=tmp_path/'annotations.json';write_json(annotation,{'episodes':[{'episode_id':i,'scene_id':'s.glb','instruction':{}} for i in (1,2,3)]})
    files=[]
    for i in (1,2,3):
        path=tmp_path/f'B{i}.json';write_json(path,[i]);files.append(path)
    output=tmp_path/'index'
    result=main(['b-index','--dataset','r2r','--annotations',str(annotation),
                 '--b1',str(files[0]),'--b2',str(files[1]),'--b3',str(files[2]),'--output',str(output)])
    assert result['counts']=={'B1':1,'B12':2,'B123':3}
    assert json.loads((output/'B123.ids.json').read_text())==['3','1','2'] or sorted(json.loads((output/'B123.ids.json').read_text()))==['1','2','3']


def test_train_cli_has_explicit_dryrun_no_automatic_download():
    with pytest.raises(SystemExit) as e:main(['train','--help'])
    assert e.value.code==0
