"""Check actual private-worker namespace/import contracts without inference."""
import argparse,json
from pathlib import Path
from graphAdapter.map_memory.worker import MemoryWorkerClient
p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args()
root=Path(a.out).absolute();case=Path('/data/zy/vln/case2')
if not root.is_relative_to(case/'outputs/graph_memory'):raise ValueError('Owned output required')
root.mkdir(parents=True,exist_ok=False);source=root/'observation_pose';source.mkdir()
profile=dict(stage='001',pose_provider='simulator_ground_truth',simulator_pose_diagnostic=True,
    pose_input_mode='provider_pose',execution_mode='archive_only')
client=MemoryWorkerClient(source,root/'map_memory',profile)
try:
 receipt=client.initialization_receipt
 assert all(receipt['input_boundary'].values())
 assert receipt['model_identity']['models_loaded'] is False
 (root/'CONTRACT.json').write_text(json.dumps(receipt,indent=2)+'\n')
 print(json.dumps(dict(status='PASS_PRIVATE_NAMESPACE_CONTRACT',input_boundary=receipt['input_boundary'],models_loaded=False)))
finally:client.close()
