from pathlib import Path
from dataclasses import replace
import sys,json,hashlib
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).parents[3]/"src/graphAdapter/map_memory/tests"))
from test_service_integration import bound_packet,seeded_service,seed_camera
from graphAdapter.map_memory.storage.store import EpisodeStore,load_episode,canonical
from poseAdapter.interfaces.mapping import measured_mapping_sample

def item(n):
 c=np.eye(4);c[0,3]=n*.01
 binding=dict(episode_id="unit",map_version=n,T_map_odom=c.tolist(),optimized_keyframes={"10":c.tolist()})
 packet,args=bound_packet(n,10,binding)
 pose=packet.to_record()["pose_record"]
 odom=np.eye(4);odom[0,3]=1
 pose["T_odom_base"]=odom.tolist()
 pose["diagnostics"]["measurement_support"].update(timestamp_ns=n,detected=70)
 pose["diagnostics"]["global_frame_link"]=dict(verified=True,epoch=0,episode_id="unit")
 pose["diagnostics"]["odometry_frame_link"]=np.eye(4).tolist()
 packet=replace(packet,pose_record=pose)
 args["committed_receipt"]["packet_record_hash"]=hashlib.sha256(canonical(packet.to_record())).hexdigest()
 sample=measured_mapping_sample(pose,binding,latest_frame_id=packet.frame_uid,episode_instance="attempt-a")
 return packet,args,sample

def test_append_does_not_replay_for_each_native_version_and_correction_is_atomic(tmp_path):
 p,a,m=item(1);store=EpisodeStore(tmp_path/"episode","unit",dataset="r2r")
 try:
  s=seeded_service(store,p,a);s.ingest(p,**a,mapping_sample=m)
  first=s.graph["views"][p.frame_uid]["T_G_base"]
  for n in range(2,5):
   p,a,m=item(n);seed_camera(s,p,a)
   result=s.ingest(p,**a,mapping_sample=m)
   assert not result["rebuild"] and result["replayed_frames"]==1
   assert s.version==1 and len(s.frames)==n
   assert s.graph["views"][p.frame_uid]["T_G_base"]==first
   assert s.graph["mapping_state"]["latest_native_map_version"]==n
  p,a,m=item(5);seed_camera(s,p,a)
  pointer=(store.root/"CURRENT.json").read_bytes()
  ready=s.prepare_endpoint(p,**a,mapping_sample=m,apply_mapping_correction=True)
  assert ready["rebuild"] and ready["replayed_frames"]==5
  assert s.mapping_chart.applied_map_version==1
  def fail(stage):
   if stage=="after_current_tmp_fsync":raise OSError("injected")
  with pytest.raises(OSError):s.publish_prepared(frame_uid=p.frame_uid,target_pose_map_version=5,fault=fail)
  assert (store.root/"CURRENT.json").read_bytes()==pointer
  assert s.mapping_chart.applied_map_version==1
  s.ingest(p,**a,mapping_sample=m,apply_mapping_correction=True)
  assert s.mapping_chart.applied_map_version==5 and s.version==5
  reader=load_episode(store.root)
  try:
   assert reader.verify()["views"]==5 and len(reader.get_trace())==4
  finally:reader.close()
 finally:store.close()

def test_chart_reloads_and_rejects_a_new_same_name_episode_instance(tmp_path):
 p,a,m=item(1);store=EpisodeStore(tmp_path/"episode","unit",dataset="r2r")
 s=seeded_service(store,p,a);s.ingest(p,**a,mapping_sample=m);store.close()
 store=EpisodeStore(tmp_path/"episode","unit",dataset="r2r",create=False)
 try:
  p,a,m=item(2);s=seeded_service(store,p,a)
  s.ingest(p,**a,mapping_sample=m)
  assert s.mapping_chart.applied_map_version==1
  p,a,m=item(3);seed_camera(s,p,a)
  with pytest.raises(ValueError,match="episode instance"):
   s.prepare_endpoint(p,**a,mapping_sample=replace(m,episode_instance="attempt-b"))
 finally:store.close()

def test_assessment_checks_history_and_current_before_expensive_work(tmp_path):
 p,a,m=item(1);store=EpisodeStore(tmp_path/"episode","unit",dataset="r2r")
 try:
  s=seeded_service(store,p,a)
  assert s.assess_mapping_correction(m,max_difference_m=.025,point_radius_m=5,T_base_camera=p.T_base_camera)["action"]=="initialize"
  s.ingest(p,**a,mapping_sample=m)
  p,a,m=item(2)
  result=s.assess_mapping_correction(m,max_difference_m=.025,point_radius_m=5,T_base_camera=p.T_base_camera)
  assert result["action"]=="append"
  assert result["max_displacement_m"]==pytest.approx(.01)
  p,a,m=item(5)
  result=s.assess_mapping_correction(m,max_difference_m=.025,point_radius_m=5,T_base_camera=p.T_base_camera)
  assert result["action"]=="correct"
  assert result["max_displacement_m"]==pytest.approx(.04)
  assert s.mapping_chart.applied_map_version==1
 finally:store.close()

def test_same_version_correction_flush_does_not_reintegrate_observation(tmp_path):
 p,a,m=item(1);store=EpisodeStore(tmp_path/"episode","unit",dataset="r2r")
 try:
  s=seeded_service(store,p,a);s.ingest(p,**a,mapping_sample=m)
  before={oid:obj["num_detections"]for oid,obj in s.scene.objects.items()}
  s.ingest(p,**a,mapping_sample=m,apply_mapping_correction=True)
  assert {oid:obj["num_detections"]for oid,obj in s.scene.objects.items()}==before
  assert len(s.frames)==1
  reader=load_episode(store.root)
  try:assert len(reader.get_trace())==0
  finally:reader.close()
 finally:store.close()
