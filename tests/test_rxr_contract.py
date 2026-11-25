"""RxR technical correction paths must address the actual phase envelope."""
import copy
import unittest

from host import rxr_contract
from host.compile import core_library
from shared.identity import ContractError


class RxRContractPathTests(unittest.TestCase):
    def test_target_error_uses_initial_or_repair_envelope_path(self):
        row = core_library('generator', 'rxr-en-us')[2]
        source = row['input']['original_instruction']
        candidate = copy.deepcopy(row['output'])
        candidate['stage_audit'][0]['target'] = {'text': None, 'candidate_quotes': []}
        with self.assertRaises(ContractError) as initial:
            rxr_contract.generator(source, candidate)
        self.assertEqual(initial.exception.to_dict()['path'], '/stage_audit/0/target')
        with self.assertRaises(ContractError) as repair:
            rxr_contract.feedback(source, {'findings': []}, {'candidate': candidate, 'responses': []})
        self.assertEqual(repair.exception.to_dict()['path'], '/candidate/stage_audit/0/target')
        self.assertEqual(repair.exception.to_dict()['code'], 'RXR_TARGET_EVIDENCE_MISSING')

    def test_duplicate_handoff_repair_points_inside_candidate(self):
        row = core_library('generator', 'rxr-en-us')[3]
        candidate = copy.deepcopy(row['output'])
        candidate['handoffs'][-1] = copy.deepcopy(candidate['handoffs'][0])
        with self.assertRaises(ContractError) as caught:
            rxr_contract.feedback(row['input']['original_instruction'], {'findings': []},
                                  {'candidate': candidate, 'responses': []})
        self.assertEqual(caught.exception.to_dict()['path'], '/candidate/handoffs')
        self.assertEqual(caught.exception.to_dict()['code'], 'RXR_HANDOFF_SEQUENCE_INVALID')


if __name__ == '__main__':
    unittest.main()
