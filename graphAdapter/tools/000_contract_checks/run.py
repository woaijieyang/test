"""Run the maintained CPU contract suite in the protected project runtime."""
import argparse,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args()
root=Path('/data/zy/vln/case2');out=Path(a.out).absolute()
if not out.is_relative_to(root/'outputs/graph_memory'):raise ValueError('Validation output must stay in owned graph output')
out.mkdir(parents=True,exist_ok=False)
targets=['src/SimulatorAdapter/tests', 'src/graphAdapter/tests/test_async_admission.py', 'src/graphAdapter/tests/test_streaming_memory_bridge.py', 'src/graphAdapter/observation_pose/tests/test_master_switch.py', 'src/graphAdapter/map_memory/tests/test_history_page_reuse.py', 'src/graphAdapter/map_memory/tests/test_storage.py', 'src/graphAdapter/evaluation/tests/test_cohort_members.py']
with(out/'pytest.log').open('x')as log:
 result=subprocess.run([sys.executable,'-B','-m','pytest','-q','-p','no:cacheprovider','--basetemp='+str(out/'scratch'),*targets],cwd=root,stdout=log,stderr=subprocess.STDOUT)
print('exit_code',result.returncode,'log',out/'pytest.log');sys.exit(result.returncode)
