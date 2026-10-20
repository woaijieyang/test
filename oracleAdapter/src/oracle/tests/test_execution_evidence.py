import hashlib
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

from oracle.adapters.habitat.native import NativeAdapter,NativeState
from oracle.verification.execution_evidence import initial_contract_errors,check_trace_stream


class ExecutionEvidence(unittest.TestCase):
    def test_equal_position_does_not_hide_wrong_initial_rotation(self):
        expected=NativeState((0,0,0),(0,0,0,1))
        actual=NativeState((0,0,0),(0,1,0,0))
        p={'maximum_prediction_error_m':1e-5,'maximum_orientation_error_rad':1e-5}
        self.assertEqual(initial_contract_errors(expected,actual,p),['initial_orientation_mismatch'])

    def test_restore_counter_observes_two_real_wrapper_calls(self):
        import numpy  # Load before sys.modules patch so mock cleanup does not unload NumPy singletons.
        common=types.ModuleType('habitat_sim.utils.common');common.quat_from_coeffs=lambda q:q
        a=NativeAdapter.__new__(NativeAdapter);a.restore_calls=0
        calls=[];agent=types.SimpleNamespace(set_state=lambda state:calls.append(state))
        a.sim=types.SimpleNamespace(get_agent=lambda _:agent)
        a.habitat_sim=types.SimpleNamespace(AgentState=types.SimpleNamespace)
        with patch.dict('sys.modules',{'habitat_sim.utils.common':common}):
            a.restore(NativeState((0,0,0),(0,0,0,1)));a.restore(NativeState((1,0,0),(0,0,0,1)))
        self.assertEqual(len(calls),2);self.assertEqual(a.restore_calls,2)

    def fixture(self):
        record={'actions':[1],'positions':[[0,0,0],[0,0,-.25]],'rotations':[[0,0,0,1]]*2,
                'boundaries':[{'reference_index':1,'action_index':1,'distance_m':0.}],
                'initialization_count':1}
        events=[{'kind':'initial','position':record['positions'][0],'rotation':record['rotations'][0]},
                {'kind':'action','index':1,'action':1,'position':record['positions'][1],'rotation':record['rotations'][1]},
                {'kind':'boundary',**record['boundaries'][0]}]
        return record,events

    def test_trace_reset_or_action_disagreement_rejected_even_with_fresh_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'executed.jsonl'
            record,events=self.fixture()
            for mutate in ('none','reset','action'):
                changed=json.loads(json.dumps(events))
                if mutate=='reset':changed.insert(1,{'kind':'reset','position':[0,0,0]})
                if mutate=='action':changed[1]['action']=3
                path.write_text(''.join(json.dumps(e)+'\n' for e in changed),encoding='utf-8')
                record['trace_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
                if mutate=='none':self.assertEqual(check_trace_stream(record,path)['actions'],1)
                else:
                    with self.assertRaises(ValueError):check_trace_stream(record,path)

    def test_legacy_missing_hash_requires_explicit_retrospective_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'executed.jsonl';record,events=self.fixture()
            path.write_text(''.join(json.dumps(e)+'\n' for e in events),encoding='utf-8')
            with self.assertRaises(ValueError):check_trace_stream(record,path)
            self.assertFalse(check_trace_stream(record,path,require_hash=False)['producer_hash_present'])
