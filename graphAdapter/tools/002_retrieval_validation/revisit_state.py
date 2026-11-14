"""Single fixed-state experiment using public measured poses and executed primitives."""
from pathlib import Path
import gzip,json,tarfile,io,hashlib,sys
import numpy as np
from PIL import Image
from graphAdapter.interfaces.host_slots import native_slot_indices

def rows(p):
    with gzip.open(p,'rt') as f:return [json.loads(line)for line in f]

def main(dest):
    reg=Path('outputs/graph_memory/candidate_detached_correction001-20261113/simulator-quality15-reuse-v3/control')
    def source(n):
        v=next(v for v in json.loads((reg/n).read_bytes()).values()if v['member'][2]=='2182')
        return Path(v['result'])
    ctrl,shadow=source('REUSED_CONTROLS.json'),source('REUSED_SHADOWS.json')
    pk=rows(shadow/'observation_packets.jsonl.gz');trace=rows(ctrl/'trace.jsonl.gz')
    chosen=None
    for model in (v for v in trace if v['kind']=='model_call'):
        n=model['frame'];current=pk[n];pose=current['pose_record']
        if n<3 or not all(p['action']['collision']is True and p['action']['action_id']==1 for p in pk[n-2:n+1]):continue
        if not all(p['pose_record']['valid'] and p['pose_record']['episode_instance']==pose['episode_instance']
                    and p['pose_record']['map_version']==pose['map_version']for p in pk[:n+1]):continue
        mats=np.asarray([p['pose_record']['T_odom_base']for p in pk[:n+1]])
        dist=np.linalg.norm(mats[:,:3,3]-mats[-1,:3,3],axis=1)
        old=[i for i in range(n) if dist[i]<.08 and np.linalg.norm(mats[i,:3,:3]-mats[-1,:3,:3])<.05 and max(dist[i:n])>=.5]
        if old:
            chosen=(model,n,old[-1],float(dist[old[-1]]),float(max(dist[old[-1]:n])));break
    assert chosen
    model,n,old,delta,excursion=chosen
    count=0
    for packet in reversed(pk[:n+1]):
        if packet['action']['action_id']!=1 or packet['action']['collision'] is not True:break
        count+=1
    dest.mkdir(parents=True,exist_ok=True);pics=dest/'images';pics.mkdir(exist_ok=True)
    native=native_slot_indices(n+1,len(model['images']));byuid={pk[i]['frame_uid']:model['images'][j]['pixel_sha256']for j,i in enumerate(native)}
    with tarfile.open(shadow/'final-map.tar.gz','r|gz')as ar:
        for m in ar:
            uid=Path(m.name).name.removesuffix('.rgb.png')
            if m.name.endswith('.rgb.png')and uid in byuid:
                data=ar.extractfile(m).read();pic=Image.open(io.BytesIO(data)).convert('RGB')
                h=hashlib.sha256(pic.mode.encode()+str(pic.size).encode()+pic.tobytes()).hexdigest()
                assert h==byuid[uid];(pics/(h+'.png')).write_bytes(data);del byuid[uid]
                if not byuid:break
    assert not byuid
    marker='<|eot_id|><|start_header_id|>assistant'
    before,after=model['prompt'].rsplit(marker,1)
    facts=[f'The estimated position and heading at step {n} are close to those at step {old}, after moving away in between.',
           f'The last {count} executed forward steps all reported collisions.']
    variants=[('recorded_exact',model['prompt'])]
    for name,ls in [('visit_only',facts[:1]),('execution_only',facts[1:]),('visit_with_execution',facts)]:
        variants.append((name,before+'\nEarlier observations from memory:\n'+'\n'.join(ls)+marker+after))
    (dest/'replay-input.json').write_text(json.dumps(dict(recorded=dict(model,images=[x['pixel_sha256']for x in model['images']]),variants=variants)))
    note=dict(member=trace[0]['episode_scope']['member'],decision=model['call_id'],step=n,old_step=old,
        same_pose_chart=pk[n]['pose_record']['episode_instance'],displacement_metres=delta,excursion_metres=excursion,
        consecutive_collisions=count,native_image_steps=native,scope='First state selected by causal revisit and consecutive actual collisions; diagnosis on one development failure')
    (dest/'binding.json').write_text(json.dumps(note,indent=2));print(note)
if __name__=='__main__':main(Path(sys.argv[1]))

