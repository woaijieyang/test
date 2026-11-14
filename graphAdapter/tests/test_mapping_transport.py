from types import SimpleNamespace
import copy
import pytest
from poseAdapter.interfaces.mapping import MappingSample
from graphAdapter.map_memory.worker import MemoryWorkerClient,validate_mapping_profile
from test_continuous_graph import item

def test_mapping_wire_roundtrip_and_tamper():
 _,_,sample=item(2)
 wire=sample.to_record()
 assert MappingSample.from_record(wire)==sample
 wire["bindings"]["T_map_odom"][0][3]+=1
 with pytest.raises(ValueError,match="identity"):MappingSample.from_record(wire)

def test_client_accepts_applied_version_without_retrying_to_native_target():
 packet,args,sample=item(2)
 client=MemoryWorkerClient.__new__(MemoryWorkerClient)
 client.profile={"pose_input_mode":"continuous"}
 client.active_episode="unit";client.count=0;calls=[]
 def call(msg):
  calls.append(msg)
  if msg["op"]=="prepare":
   assert MappingSample.from_record(msg["mapping_sample"])==sample
   return dict(result=dict(duplicate=False,target_pose_map_version=1,candidate_hash="candidate",
                           mapping_correction_applied=False))
  return dict(result=dict(snapshot_id="s",versions={"pose_map_version":1},cutoff={"capture_seq":2,"event_seq":20}))
 client.call=call
 def forbidden(*a,**k):raise AssertionError("Redundant native snapshot read")
 adapter=SimpleNamespace(get_mapping_frame_snapshot=lambda *a,**k:sample,get_frame_snapshot=forbidden)
 result=client.consume(packet,args["committed_receipt"],pose_adapter=adapter)
 assert [x["op"]for x in calls]==["prepare","commit"]
 assert result["versions"]["pose_map_version"]==1 and client.count==1

def test_continuous_mode_requires_explicit_policy_and_native_capability():
 with pytest.raises(ValueError):validate_mapping_profile({"pose_input_mode":"typo"})
 with pytest.raises(ValueError):validate_mapping_profile({"pose_input_mode":"continuous"})
 assert validate_mapping_profile({})=="native_corrected"
 assert validate_mapping_profile({"pose_input_mode":"continuous","correction":{
  "max_correction_difference_m":.025,"mapping_point_radius_m":5.}})=="continuous"
 packet,args,_=item(1)
 client=MemoryWorkerClient.__new__(MemoryWorkerClient)
 client.profile={"pose_input_mode":"continuous"};client.active_episode="unit"
 with pytest.raises(RuntimeError,match="interface"):
  client.consume(packet,args["committed_receipt"],pose_adapter=SimpleNamespace())
