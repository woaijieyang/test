import sys,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from checkpoint_choice import pools,summarize,idle_gpus,LEAVES

class CheckpointChoice(unittest.TestCase):
    def setUp(self):
        self.leaves={k:[str(i)] for i,k in enumerate(LEAVES)}
        self.m={'run_id':'fixture','claim_scope':'fixture','expected_tasks':[{'dataset':'r2r','task_key':f'r2r|val_unseen|en|scene|{i}|-'} for i in range(7)]}
        self.rows=[{'dataset':'r2r','task_key':x['task_key'],'status':'completed','metrics':{'sr':int(i==0),'spl':0.,'ndtw':.5,'ne':float(i),'oracle_sr':1.}} for i,x in enumerate(self.m['expected_tasks'])]
    def test_namespace_alias_gets_distinct_view_and_preserves_old(self):
        import tempfile,hashlib
        from checkpoint_choice import scene_view
        with tempfile.TemporaryDirectory(dir=ROOT/'.cache') as tmp:
            base=Path(tmp);a=base/'raw';b=base/'mounted';a.mkdir();b.mkdir()
            for folder in (a,b):
                (folder/'s.glb').write_bytes(b'scene');(folder/'s.navmesh').write_bytes(b'mesh')
            def profile(folder):
                return {'assets':{'mp3d/s/s.glb':{'scene_path':str(folder/'s.glb'),'scene_sha256':hashlib.sha256(b'scene').hexdigest(),'navmesh_path':str(folder/'s.navmesh'),'navmesh_sha256':hashlib.sha256(b'mesh').hexdigest()}}}
            with patch('checkpoint_choice.ROOT',base):
                old=scene_view(profile(a));new=scene_view(profile(b))
                self.assertNotEqual(old,new)
                self.assertEqual((old/'mp3d/s/s.glb').resolve(),a/'s.glb')
                self.assertEqual((new/'mp3d/s/s.glb').resolve(),b/'s.glb')
                self.assertEqual(scene_view(profile(b)),new)

    def test_shared_budget_requires_full_quota_plus_headroom(self):
        from checkpoint_choice import shared_gpus
        with patch('checkpoint_choice.subprocess.check_output',return_value='0, 49140, 0\n4, 49140, 16000\n5, 49140, 22516\n6, 49140, 22517\n7, 49140, 48000\n'):
            self.assertEqual(shared_gpus(),[4,5])

    def test_full_and_cumulative_disjoint(self):
        p=pools(self.leaves);self.assertEqual(p['A1+A2'],['0','1']);self.assertEqual(len(p['Full']),7)
    def test_duplicate_leaf_rejected(self):
        self.leaves['A2']=['0']
        with self.assertRaises(ValueError):pools(self.leaves)
    def test_exact_subset_mean(self):
        s=summarize(self.m,self.rows,self.leaves)
        self.assertEqual(s['A1+A2']['datasets']['r2r']['metrics']['sr'],.5)
        self.assertAlmostEqual(s['Full']['datasets']['r2r']['metrics']['sr'],1/7)
    def test_partial_is_not_complete(self):
        self.assertFalse(summarize(self.m,self.rows[:-1],self.leaves)['Full']['complete'])
    def test_duplicate_result_rejected(self):
        with self.assertRaises(ValueError):summarize(self.m,self.rows+self.rows[:1],self.leaves)
    def test_wrong_instruction_identity_rejected(self):
        self.rows[0]['task_key']=self.rows[0]['task_key'][:-1]+'other'
        with self.assertRaises(ValueError):summarize(self.m,self.rows,self.leaves)
    def test_idle_allocation_excludes_active_and_unapproved(self):
        output='0, UUID0, 0, 0\n4, UUID4, 900, 0\n5, UUID5, 0, 0\n6, UUID6, 0, 99\n7, UUID7, 0, 0\n'
        with patch('checkpoint_choice.subprocess.check_output',side_effect=[output,'UUID4\n']):
            self.assertEqual(idle_gpus(),[5,7])

if __name__=='__main__':unittest.main()
