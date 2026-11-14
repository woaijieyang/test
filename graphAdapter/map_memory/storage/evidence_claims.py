"""Describe observed class support without promoting source associations to ground truth."""
from collections import defaultdict

def describe_association(obj,sources,*,filtered=False):
    groups=defaultdict(list)
    for source in sources:groups[int(source['source_class_id'])].append(source)
    native=(obj.get('attributes')or{}).get('class_id',())
    all_classes=sorted(set(int(x) for x in native)|set(groups))
    support=[]
    for class_id,items in sorted(groups.items()):
        best=min(items,key=lambda x:(-x['confidence'],x['capture_seq'],x['detection_index']))
        support.append(dict(source_class_id=class_id,detection_count=len(items),
            distinct_frame_count=len({x['frame_uid'] for x in items}),
            representative_member=best['member'],members=[x['member'] for x in items]))
    mixed=len(all_classes)>1
    return dict(evidence_contract_version=2,
        identity_scope='inactive_association' if obj['status']!='active' else 'mixed_class_association' if mixed else 'estimated_object_association',
        geometry_claim_scope='fused_association_not_class_specific',
        label_claim_scope='model_aggregate_not_verified_instance_label',
        evidence_selection='source_subset' if filtered else 'all_object_members',
        all_object_source_class_ids=all_classes,class_evidence=support,
        single_physical_object_verified=False)
