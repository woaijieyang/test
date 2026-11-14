from dataclasses import replace
import pytest
from graphAdapter.map_memory.retrieval.contracts import ViewRef,Candidate,CandidateResult
from graphAdapter.map_memory.retrieval.bundles import build_bundles
from graphAdapter.map_memory.retrieval.selector import select_history


def view(n,*,image=None):return ViewRef('ep','snap',f'f{n}',n,n*10,n-1,image or f'h{n}',f'host{n}',None,0,(),None)
def candidates(order,all_views=None):
    values=tuple(view(n)for n in (all_views or range(1,20)))
    by_id={v.capture_seq:v for v in values}
    return CandidateResult('snap',values,tuple(Candidate(by_id[n],1./(60+i),(),None,None,(),('rgb',))for i,n in enumerate(order,1)),{},(),())
def edge(a,b,kind='temporal_next'):return {'id':f'{kind}:{a}:{b}','src':f'f{a}','dst':f'f{b}','type':kind}
def index(edges):return {'edges':edges,'visibility_edges':(),'entities':(),'scene_epoch':None}

def test_R02_bundle_only_follows_stored_edges_and_never_distance():
    c=candidates([5]);bundles=build_bundles(c,index([edge(4,5),edge(5,6),edge(5,6,'traversed')]),pose_map_version=0)
    b=bundles[0]
    assert tuple(v.capture_seq for v in b.views)==(4,5,6)
    assert b.edge_types==('temporal_next','traversed') and b.execution_refs==('traversed:5:6',)
    singleton=build_bundles(c,index([]),pose_map_version=0)[0]
    assert singleton.selection_reason=='singleton' and len(singleton.views)==1


def test_R03_future_neighbor_and_two_hop_are_not_added():
    c=candidates([5],all_views=range(1,7))
    b=build_bundles(c,index([edge(4,5),edge(3,4),edge(5,7)]),pose_map_version=0)[0]
    assert tuple(v.capture_seq for v in b.views)==(4,5)
    assert 'missing_after' in b.missing_evidence

@pytest.mark.parametrize('budget',[4,8,12])
def test_R04_current_recent_budget_and_R05_final_chronology(budget):
    c=candidates([5,2,10,14]);bundles=build_bundles(c,index([edge(i,i+1)for i in range(1,19)]),pose_map_version=0)
    result=select_history(c,bundles,view(20),budget=budget)
    assert result.fallback_reason is None and len(result.slots)<=budget
    assert result.slots[-1].frame_uid=='f20'
    assert [v.capture_seq for v in result.slots]==sorted(v.capture_seq for v in result.slots)
    recent=min(3,max(1,(budget-1)//2))
    assert set(range(20-recent,20))<={v.capture_seq for v in result.slots}
    assert len({v.image_hash for v in result.slots})==len(result.slots)

@pytest.mark.parametrize('budget',[1,2])
def test_R04_small_budget_requests_unchanged_host_sampler(budget):
    c=candidates([5]);result=select_history(c,(),view(20),budget=budget)
    assert result.fallback_reason=='budget_le_two' and result.slots==()


def test_R04_current_duplicate_replaced_by_earlier_real_endpoint():
    c=candidates([3]);c=replace(c,views=tuple(replace(v,image_hash='h20')if v.capture_seq>=18 else v for v in c.views))
    result=select_history(c,build_bundles(c,index([]),pose_map_version=0),view(20),budget=8)
    ids={v.capture_seq for v in result.slots}
    assert {15,16,17,20}<=ids and 18 not in ids and 19 not in ids


def test_incomplete_bundle_is_explicit_singleton_without_relation_claim():
    c=candidates([5]);b=build_bundles(c,index([edge(4,5),edge(5,6)]),pose_map_version=0)
    result=select_history(c,b,view(20),budget=4)
    assert result.groups[0].selection_reason=='singleton_out_of_budget'
    assert result.groups[0].edge_types==() and len(result.groups[0].views)==1
    assert ('f5','out_of_budget') in result.rejected


def test_empty_global_pool_requests_original_uniform_fallback():
    c=candidates([]);result=select_history(c,(),view(20),budget=8)
    assert result.fallback_reason=='no_global_candidates' and result.slots==()


def test_flat_mode_never_expands_neighbors():
    c=candidates([5]);b=build_bundles(c,index([edge(4,5),edge(5,6)]),pose_map_version=0,expand=False)
    assert len(b[0].views)==1 and not b[0].edge_types


def test_long_history_one_grounded_seed_preserves_native_context_in_unspent_slots():
    c=candidates([5]);groups=build_bundles(c,index([]),pose_map_version=0)
    result=select_history(c,groups,view(20),budget=8)
    assert len(result.slots)==8
    assert [g.seed_ref for g in result.groups]==['f5']
    assert {17,18,19,20} <= {v.capture_seq for v in result.slots}
    assert any(v.capture_seq in (1,3,6,9,12,15) for v in result.slots)
    assert len({v.image_hash for v in result.slots})==8


def test_single_substitution_preserves_current_and_all_other_native_slots():
    from graphAdapter.map_memory.retrieval.selector import select_grounded_single_slot
    c=candidates([17],all_views=range(1,34));c=replace(c,ranked=(replace(c.ranked[0],matched_categories=('bed',)),))
    result=select_grounded_single_slot(c,view(34),budget=8)
    assert [v.capture_seq-1 for v in result.slots]==[0,4,9,16,18,23,28,33]
    assert len(result.groups)==1 and result.groups[0].seed_ref=='f17'
    assert select_grounded_single_slot(replace(c,ranked=()),view(34),budget=8).fallback_reason


def test_linked_visual_memory_recalls_without_category_with_exact_edge():
    from graphAdapter.map_memory.retrieval.selector import select_linked_view
    c=candidates([5,11]);c=replace(c,channels={'Q':('f11',),'V':('f5',),'C':()})
    idx=index([edge(11,12,'traversed'),edge(12,13),edge(12,40)])
    # Native sampler spans 0 through len-1, excluding its endpoint for history.
    assert select_linked_view(c,view(20),idx,budget=8).fallback_reason
    c=candidates([5,12]);c=replace(c,channels={'Q':('f12',),'V':('f5',),'C':()})
    result=select_linked_view(c,view(20),idx,budget=8)
    assert [v.capture_seq for v in result.slots]==[1,3,6,9,11,12,17,20]
    assert result.groups[0].execution_refs==('traversed:11:12',)
    assert select_linked_view(c,view(20),index([]),budget=8).fallback_reason


def test_linked_read_preserves_less_redundant_displaced_observation():
    from graphAdapter.map_memory.retrieval.selector import select_linked_view
    import numpy as np
    c=candidates([12]);c=replace(c,channels={'Q':('f12',),'V':(),'C':()})
    idx=index([edge(11,12,'traversed')])
    near=np.array([1.,0.]);different=np.array([0.,1.])
    # f12 copies retained f11 while outgoing f14 is visually distinct.
    current=select_linked_view(c,view(20),idx,budget=8,full_image_feature=lambda uid:different if uid=='f14'else near)
    assert current.fallback_reason and not current.slots
    valid=select_linked_view(c,view(20),idx,budget=8,full_image_feature=lambda uid:different if uid=='f12'else near)
    assert valid.groups[0].seed_ref=='f12' and len(valid.slots)==8

def test_flat_control_never_traverses_graph_relations():
    class NoRelations:
        def get(self,*args):raise AssertionError('Flat selection inspected graph neighborhoods')
    c=candidates([5,2]);flat=build_bundles(c,NoRelations(),pose_map_version=0,expand=False)
    assert [(g.seed_ref,len(g.views),g.edge_types,g.missing_evidence)for g in flat]==[
        ('f5',1,(),('missing_before','missing_after')),('f2',1,(),('missing_before','missing_after'))]
