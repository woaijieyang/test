import unittest
from oracle.verification.global_bounded_mapping import verify_index


class GlobalMappingAuditTests(unittest.TestCase):
    def test_held_and_unchanged_records_cannot_gain_hidden_proposal(self):
        parent={'a':{'source_record_sha256':'a'},'b':{'source_record_sha256':'b'},'c':{'source_record_sha256':'c'}}
        index=[{'task_key':'a','legacy_source_record_sha256':'a','status':'HELD114_ORIGINAL_AND_FAILURE_PRESERVED','proposal_path':None,'proposal_sha256':None,'adopted':False},
               {'task_key':'b','legacy_source_record_sha256':'b','status':'UNCHANGED_BASELINE_NO_MAPPING_FAULT','proposal_path':None,'proposal_sha256':None,'adopted':False},
               {'task_key':'c','legacy_source_record_sha256':'c','status':'UNRESOLVED_FIXED_SOURCE_FAMILY_PRESERVED','proposal_path':'c.json','proposal_sha256':'hash','adopted':False}]
        verify_index(index,parent,{'a','c'},{'a'})
        index[0]['proposal_path']='override.json'
        with self.assertRaises(ValueError):verify_index(index,parent,{'a','c'},{'a'})

    def test_missing_or_duplicate_identity_rejected(self):
        with self.assertRaises(ValueError):verify_index([],{'x':{'source_record_sha256':'x'}},set(),set())
