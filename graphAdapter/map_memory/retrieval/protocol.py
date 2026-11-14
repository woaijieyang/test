"""Standard-library-only, immutable host/private-worker read wire contract."""
from dataclasses import dataclass
import json,re

MODES=frozenset(('uniform_original','uniform_tagged','flat_equal_budget','graph_image_only','graph_image_facts','facts_only','native_plus_attachment'))
QUERY_FIELDS=frozenset(('episode_uid','snapshot_id','current_frame_uid','current_capture_seq','cutoff_capture_seq',
    'cutoff_event_seq','instruction','current_position','pose_map_version','last_reasoning','last_reasoning_event_seq','decision_event_seq'))

@dataclass(frozen=True)
class FrozenMemoryRead:
    request_json: bytes

    @classmethod
    def create(cls,request,*,max_bytes=1024*1024):
        data=json.dumps(request,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
        if len(data)>max_bytes:raise ValueError('Read request exceeds byte budget')
        value=json.loads(data)
        if set(value)!= {'protocol_version','request_id','episode_instance','mode','budget','query'} or type(value['protocol_version']) is not int or value['protocol_version'] not in (1,2,3):
            raise ValueError('Unsupported read request schema')
        if not isinstance(value['request_id'],str)or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',value['request_id']):
            raise ValueError('Opaque bounded read request ID required')
        if not isinstance(value['episode_instance'],str)or not 1<=len(value['episode_instance'])<=256:
            raise ValueError('Explicit bounded episode session required')
        if value['mode']not in MODES or type(value['budget'])is not int or value['budget']<1:
            raise ValueError('Declared retrieval mode and original image budget required')
        query=value['query']
        required={'episode_uid','snapshot_id','current_frame_uid','current_capture_seq','cutoff_capture_seq','cutoff_event_seq','instruction'}
        allowed=QUERY_FIELDS
        if value['protocol_version']==3:
            allowed=(QUERY_FIELDS-{'current_position','pose_map_version'})|{'decision_id'}
            required.update(('decision_id','decision_event_seq'))
        if not isinstance(query,dict)or not required<=set(query)or not set(query)<=allowed:
            raise ValueError('Unsupported query fields')
        for key in ('episode_uid','current_frame_uid','instruction'):
            if not isinstance(query[key],str)or not query[key]:raise ValueError('Missing read query identity/text')
        if not isinstance(query['snapshot_id'],str)or not re.fullmatch('[a-f0-9]{64}',query['snapshot_id']):
            raise ValueError('Read must pin a concrete snapshot')
        for key in ('current_capture_seq','cutoff_capture_seq','cutoff_event_seq'):
            if type(query[key])is not int or query[key]<0:raise ValueError('Invalid read query cutoff')
        if query['cutoff_capture_seq']>query['current_capture_seq']:raise ValueError('Future read cutoff')
        if query.get('current_position') is not None:
            raise ValueError('Only the pinned reader can supply a position')
        version=query.get('pose_map_version')
        if version is not None and (type(version)is not int or version<0):
            raise ValueError('Invalid legacy pose version')
        decision=query.get('decision_event_seq')
        if decision is not None and (type(decision)is not int or decision<query['cutoff_event_seq']):
            raise ValueError('Invalid decision clock')
        if value['protocol_version']==3 and (type(query['decision_id']) is not int or query['decision_id']<1
                or decision is None or decision<=query['cutoff_event_seq']):
            raise ValueError('A read must belong to a subsequent decision')
        reasoning=query.get('last_reasoning');event=query.get('last_reasoning_event_seq')
        if reasoning is None:
            if event is not None:raise ValueError('Reasoning event without text')
        elif (not isinstance(reasoning,str) or not reasoning.strip() or type(event)is not int
                or not 0<event<(decision if decision is not None else query['cutoff_event_seq'])):
            raise ValueError('Invalid reasoning text or clock')
        return cls(data)

    @property
    def request(self):return json.loads(self.request_json)
    @property
    def frame_uid(self):return self.request['query']['current_frame_uid']

    def validate_reply(self,reply):
        request=self.request;query=request['query']
        expected=dict(request_id=request['request_id'],episode_uid=query['episode_uid'],
            episode_instance=request['episode_instance'],snapshot_id=query['snapshot_id'])
        if request['protocol_version']==3:
            expected.update(decision_id=query['decision_id'],decision_event_seq=query['decision_event_seq'],
                            current_frame_uid=query['current_frame_uid'],current_capture_seq=query['current_capture_seq'],
                            mode=request['mode'],read_only=True)
        if not isinstance(reply,dict)or any(type(reply.get(k))is not type(v) or reply.get(k)!=v for k,v in expected.items()):
            raise ValueError('Read reply identity differs from its own request')
        return json.loads(json.dumps(reply,allow_nan=False))


DEFAULT_READ_SETTINGS=dict(enabled=True,mode='graph_image_only',read_timeout_seconds=5.0,
    query_cache_bytes=4*1024*1024,feature_cache_bytes=64*1024*1024,overlap=16,batch_windows=16,
    max_fact_tokens=256, evidence_policy='ranked')

def retrieval_settings(profile):
    """Read is opt-in at002;001 and off cannot enable it by residual settings."""
    value=profile.get('retrieval')
    if value is None:return None
    if not isinstance(value,dict)or type(value.get('enabled'))is not bool:
        raise ValueError('Explicit retrieval enabled boolean required')
    if 'suppress_same_frame_repeat' in value and type(value['suppress_same_frame_repeat']) is not bool:
        raise ValueError('Same-frame repeat policy must be boolean')
    if value.get('suppress_same_frame_repeat') and value.get('evidence_policy')!='additive_text':
        raise ValueError('Same-frame control requires the declared additional evidence profile')
    if 'landmark_repeat' in value and (value.get('evidence_policy')!='dynamic_evo_context'
            or value['landmark_repeat'] not in ('once_per_reasoning','object_once_per_reasoning')):
        raise ValueError('Unsupported source-photo repeat policy')
    if 'approach_photo_support' in value and (value.get('evidence_policy')!='historical_approach'
            or value.get('mode')!='native_plus_attachment' or value['approach_photo_support']!='shared_depth'):
        raise ValueError('Unsupported historical photo support policy')
    if 'landmark_query' in value and (value.get('evidence_policy')!='dynamic_evo_context'
            or value['landmark_query']!='current_plan'):
        raise ValueError('Current-plan landmark query requires dynamic graph evidence')
    if 'context_bundle' in value and (value.get('evidence_policy')!='evo_topology' or type(value['context_bundle']) is not bool):
        raise ValueError('Context bundle requires an explicit Evo profile')
    if 'attachment_feature_cache_bytes' in value and (value.get('evidence_policy')!='evo_topology'
            or type(value['attachment_feature_cache_bytes']) is not int or value['attachment_feature_cache_bytes']<0):
        raise ValueError('Explicit nonnegative Evo attachment feature cache budget required')
    if 'locate_door_regions' in value and (type(value['locate_door_regions']) is not bool or value.get('structural_door_regions') is not True):
        raise ValueError('Door pixel support requires source-bound door regions')
    if 'structural_door_regions' in value and (type(value['structural_door_regions']) is not bool or value.get('grounded_node_summary') is not True):
        raise ValueError('Door regions require a grounded map and bound historical views')
    if 'anchor_routes' in value and (type(value['anchor_routes']) is not bool or value.get('source_node_labels') is not True or value.get('topology_relations')):
        raise ValueError('Named anchor routes require source labels and a single route compiler')
    if 'source_node_labels' in value and (type(value['source_node_labels']) is not bool or value.get('grounded_node_summary') is not True):
        raise ValueError('Source-based labels require grounded node descriptions')
    if 'grounded_node_summary' in value and (type(value['grounded_node_summary']) is not bool or value.get('current_camera_overlay') is not True):
        raise ValueError('Grounded node descriptions require current camera overlay')
    if 'current_camera_overlay' in value and (type(value['current_camera_overlay']) is not bool or value.get('global_map') is not True):
        raise ValueError('Camera overlay requires an explicit global map')
    if 'global_map' in value and (value.get('evidence_policy')!='evo_topology' or type(value['global_map']) is not bool
            or value.get('global_map') and value.get('topology_image')):
        raise ValueError('Use one explicit map image mode in an Evo profile')
    if 'topology_image' in value and (value.get('evidence_policy')!='evo_topology' or type(value['topology_image']) is not bool):
        raise ValueError('Topology image requires an explicit boolean Evo profile')
    if 'topology_relations' in value and (value.get('evidence_policy')!='evo_topology' or type(value['topology_relations']) is not bool):
        raise ValueError('Topology relations require an explicit boolean Evo profile')
    if 'landmark_ambiguity' in value and (value['landmark_ambiguity'] not in ('omit_competing_instances','check_historical_anchors')
            or value.get('landmark_query')!='current_plan' or value.get('evidence_policy')!='dynamic_evo_context'):
        raise ValueError('Competing-instance handling requires ranked current-plan landmarks')
    if 'native_object' in value and (value['native_object']!='skip_present' or value.get('evidence_policy')!='dynamic_evo_context'):
        raise ValueError('Native object evidence requires dynamic graph retrieval')
    if 'landmark_position' in value and (value.get('evidence_policy')!='dynamic_evo_context'
            or value['landmark_position']!='fused_center'):
        raise ValueError('Unsupported landmark position mode')
    if 'context_admission' in value:
        if value.get('evidence_policy')!='dynamic_evo_context' or value['context_admission'] not in ('all_verified','landmark_or_collision','native_plan_photo'):
            raise ValueError('Unknown dynamic-context admission mode')
        if value['context_admission']=='native_plan_photo' and value.get('landmark_query')!='current_plan':
            raise ValueError('Native plan photo requires current-plan source binding')
    if set(value)-(set(DEFAULT_READ_SETTINGS)|{'suppress_same_frame_repeat','context_admission','landmark_repeat','approach_photo_support','landmark_position','landmark_query','native_object','landmark_ambiguity','topology_relations','topology_image','context_bundle','global_map','current_camera_overlay','attachment_feature_cache_bytes','grounded_node_summary','structural_door_regions','locate_door_regions','source_node_labels','anchor_routes'}):raise ValueError('Unsupported retrieval settings')
    if not value['enabled']:return None
    if profile.get('stage')!='002' or profile.get('execution_mode','live')!='live' or profile.get('async_admission')is not True:
        raise ValueError('Retrieval requires explicit002 live mapping and serialized asynchronous admission')
    if profile.get('pose_provider')!='simulator_ground_truth' or profile.get('pose_input_mode')!='provider_pose':
        raise ValueError('Current read deployment requires the explicit Simulator pose interface')
    result=dict(DEFAULT_READ_SETTINGS,**value)
    if result['evidence_policy'] not in ('ranked', 'instruction_grounded','grounded_single_slot','linked_history_single_slot','linked_view_gain','additive_text','context_text','landmark_attachment','evo_event_attachment','dynamic_evo_context','historical_approach','evo_topology'):
        raise ValueError('Unknown retrieval evidence policy')
    if result['evidence_policy']=='historical_approach' and result['mode'] not in ('facts_only','native_plus_attachment'):
        raise ValueError('Approach evidence requires original visual slots')
    if result['evidence_policy'] in ('additive_text','context_text') and result['mode']!='facts_only':
        raise ValueError('Additional text requires native image sampling')
    if result['evidence_policy']!='historical_approach' and ((result['mode']=='native_plus_attachment') != (result['evidence_policy'] in ('landmark_attachment','evo_event_attachment','dynamic_evo_context','evo_topology'))):
        raise ValueError('Separate native-plus-attachment profile required for additional visual material')
    if result['mode']not in MODES:raise ValueError('Unknown retrieval mode')
    import math
    timeout=result['read_timeout_seconds']
    if type(timeout)not in(int,float)or not math.isfinite(timeout)or timeout<=0:
        raise ValueError('Finite positive read timeout required')
    for key in ('query_cache_bytes','feature_cache_bytes','overlap','max_fact_tokens'):
        if type(result[key])is not int or result[key]<0:raise ValueError('Nonnegative retrieval budget required: '+key)
    if type(result['batch_windows'])is not int or result['batch_windows']<1:raise ValueError('Positive text batch budget required')
    return result


def native_slot_indices(observations, budget):
    import numpy as np
    if type(observations) is not int or observations < 1:
        raise ValueError('At least the current observation is required')
    if type(budget) is not int or budget < 1:
        raise ValueError('The checkpoint image budget must be positive')
    padding = max(0, budget - observations)
    last = observations + padding - 1
    history = np.linspace(0, last, num=budget-1, endpoint=False, dtype=int)
    return tuple(None if i < padding else int(i)-padding for i in history) + (observations-1,)



def sample_native_rgb(images,num_frames=8,width=512,height=512):
    """Copy only the selected host RGB observations, preserving original padding and order."""
    from PIL import Image
    indices=native_slot_indices(len(images),num_frames)
    return [Image.new("RGB",(width,height)) if index is None else images[index].copy()
            for index in indices]
