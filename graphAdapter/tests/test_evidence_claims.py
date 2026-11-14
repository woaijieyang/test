from graphAdapter.map_memory.storage.evidence_claims import describe_association

def source(member,cls,frame,confidence,index=0):
 return dict(member=member,source_class_id=cls,frame_uid=frame,capture_seq=int(frame[1:]),confidence=confidence,detection_index=index)

def test_mixed_group_retains_class_specific_evidence_without_single_identity_claim():
 obj=dict(status='active',attributes={'class_id':[101,101,124]})
 values=[source('a',101,'f1',.8),source('b',101,'f2',.7),source('c',124,'f2',.9,1)]
 result=describe_association(obj,values)
 assert result['identity_scope']=='mixed_class_association' and not result['single_physical_object_verified']
 assert result['class_evidence'][0]['members']==['a','b'] and result['class_evidence'][0]['representative_member']=='a'
 assert result['class_evidence'][1]['members']==['c']
 assert result['geometry_claim_scope']=='fused_association_not_class_specific'

def test_filtering_one_source_cannot_hide_global_class_conflict():
 obj=dict(status='active',attributes={'class_id':[101,124]})
 result=describe_association(obj,[source('a',101,'f1',.8)],filtered=True)
 assert result['identity_scope']=='mixed_class_association'
 assert result['all_object_source_class_ids']==[101,124] and result['evidence_selection']=='source_subset'
 assert len(result['class_evidence'])==1
