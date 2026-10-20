import copy,unittest
from oracle.research.mapping_factorial import variant_task


class MappingFactorialTests(unittest.TestCase):
    def test_factorial_reports_axes_separately_and_keeps_endpoint_gate_failure(self):
        from oracle.research.mapping_factorial import summarize_factorial
        good='PASS_CONTINUOUS_REFERENCE_AND_ENDPOINT_GATES';bad='ROUTE_WITNESS_ONLY_ENDPOINT_SOURCE_GATE_FAIL'
        rows={k:[{'task_key':'x','status':v}] for k,v in {
            'original_map_uncached':bad,'original_map_cache':bad,
            'candidate_map_uncached':good,'candidate_map_cache':good}.items()}
        r=summarize_factorial(rows,['x'])
        self.assertEqual(r['cells']['original_map_uncached']['strict_pass'],0)
        self.assertEqual(r['contrasts']['mapping_at_uncached']['recovered'],['x'])
        self.assertEqual(r['contrasts']['cache_at_candidate_mapping']['recovered'],[])
        rows['candidate_map_cache']=[]
        with self.assertRaises(ValueError):summarize_factorial(rows,['x'])

    def task(self):
        return {'task_key':'train:x','dataset':'landmark_rxr','targets':[[0,0,0],[1,0,0]],
            'start_rotation':[0,0,0,1],'raw_heading':0.,'raw_subpath_headings':[0.],
            'segments':[{'index':0,'start':0,'end':1}], 'source_record_sha256':'raw',
            'original_viewpoint_path':['a','b'],'profile_sha256':'profile','geometry_catalog_sha256':'geometry',
            'privileges':['true_pose','goal','reference_path','navigation_mesh','source_geometry','landmark_annotations','official_actions'],
            'official_demonstration':{'actions':[1,0]},'reference_action_pose_relation':{'numeric_initial_pose_match':True}}

    def test_mapping_axis_only_changes_targets_and_explicit_provenance(self):
        t=self.task();before=copy.deepcopy(t);p={'proposed_targets':[[.1,0,0],[1,0,0]]}
        old=variant_task(t,p,False,'source','proposal')
        new=variant_task(t,p,True,'source','proposal')
        self.assertEqual(t,before);self.assertEqual(old['targets'],t['targets'])
        self.assertEqual(new['targets'],p['proposed_targets'])
        for field in ['start_rotation','raw_heading','raw_subpath_headings','segments','source_record_sha256','original_viewpoint_path','profile_sha256']:
            self.assertEqual(old[field],new[field])
        self.assertNotIn('official_demonstration',old);self.assertNotIn('official_demonstration',new)
        self.assertNotIn('official_actions',new['privileges'])
        self.assertEqual(old['privileges'],new['privileges'])

    def test_rejects_r2r_and_missing_reference_in_proposal(self):
        t=self.task();t['dataset']='r2r'
        with self.assertRaises(ValueError):variant_task(t,{'proposed_targets':t['targets']},True,'s','p')
        t['dataset']='landmark_rxr'
        with self.assertRaises(ValueError):variant_task(t,{'proposed_targets':[[0,0,0]]},True,'s','p')

    def test_effective_method_retains_explicit_cache_variant_identity(self):
        from oracle.research.full_worker import effective_method
        task={'method_selection':{'official_policy':'none'},'privileges':[]}
        self.assertEqual(effective_method(task,{'base_method':{'id':'bounded_search_cache_v1'}})['id'],'bounded_search_cache_v1')
