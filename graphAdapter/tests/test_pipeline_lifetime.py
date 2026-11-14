from pathlib import Path
import sys,threading
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).parents[3]/'src/graphAdapter/map_memory/tests'))
from test_service_integration import bound_packet,seeded_service,seed_camera
from graphAdapter.map_memory.storage.store import EpisodeStore,load_episode
from graphAdapter.map_memory.geometry.core import TSDFSubmapManager
from graphAdapter.map_memory.perception.scene import MemoryOnlyScene

@pytest.mark.parametrize('correction',[False,True])
@pytest.mark.parametrize('failure',['geometry','scene','both',None])
def test_pipeline_join_rollback_and_retry(tmp_path,monkeypatch,failure,correction):
 store=EpisodeStore(tmp_path/'episode','unit',dataset='r2r')
 try:
  binding=dict(episode_id='unit',map_version=0,optimized_keyframes={'10':np.eye(4).tolist()})
  first,a1=bound_packet(1,10,binding);s=seeded_service(store,first,a1);s.resource_limits['parallel_geometry_scene']=True;s.ingest(first,**a1)
  original=(store.root/'CURRENT.json').read_bytes()
  corrected=np.eye(4);corrected[0,3]=.1 if correction else 0.
  binding=dict(episode_id='unit',map_version=1 if correction else 0,optimized_keyframes={'10':corrected.tolist()})
  second,a2=bound_packet(2,10,binding);seed_camera(s,second,a2)
  geo=TSDFSubmapManager.integrate;scene=MemoryOnlyScene.fuse
  geo_entered=threading.Event();scene_entered=threading.Event();threads=[]
  def checked_geo(*a,**kw):
   threads.append(threading.current_thread())
   geo_entered.set()
   assert scene_entered.wait(5),'scene did not overlap geometry'
   value=geo(*a,**kw)
   if failure in ('geometry','both'):raise RuntimeError('injected geometry failure')
   return value
  def checked_scene(*a,**kw):
   scene_entered.set()
   assert geo_entered.wait(5),'geometry did not overlap scene'
   value=scene(*a,**kw)
   if failure in ('scene','both'):raise RuntimeError('injected scene failure')
   return value
  with monkeypatch.context() as m:
   m.setattr(TSDFSubmapManager,'integrate',checked_geo)
   m.setattr(MemoryOnlyScene,'fuse',checked_scene)
   if failure:
    with pytest.raises(RuntimeError,match='injected'):
     s.prepare_endpoint(second,**a2)
   else:
    result=s.prepare_endpoint(second,**a2)
    assert result['processing_metrics']['geometry_queue_peak']<=2
    assert result['processing_metrics']['geometry_frame_uids']==result['processing_metrics']['scene_frame_uids']
    assert result['rebuild']==correction
  assert all(not t.is_alive() for t in threads)
  if failure=='both':
   assert {x['branch'] for x in s.last_branch_failures}=={'geometry','scene'}
   assert all(x['frame_uid'] for x in s.last_branch_failures)
   assert all('injected' in x['message'] for x in s.last_branch_failures)
  assert (store.root/'CURRENT.json').read_bytes()==original
  assert not list((store.root/'.pending').glob('tile-replay-*'))
  s.ingest(second,**a2)
  reader=load_episode(store.root)
  try:
   assert reader.verify()['views']==2
  finally:reader.close()
 finally:store.close()


def test_parallel_flag_rejected_before_worker_spawn():
 from graphAdapter.map_memory.worker import validate_mapping_profile
 for value in ('false',1,None):
  with pytest.raises(ValueError,match='boolean'):
   validate_mapping_profile({'resources':{'parallel_geometry_scene':value}})
 assert validate_mapping_profile({'resources':{'parallel_geometry_scene':False}})=='native_corrected'
