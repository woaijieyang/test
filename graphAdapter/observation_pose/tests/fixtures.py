"""CPU runtime fixture for real producer/bridge contracts; not native tracking evidence."""
import numpy as np
from poseAdapter import PoseAdapter,PoseEstimate

def sensor_spec(size=8):
    projection=[[1,0,0,0],[0,1,0,0],[0,0,-1,-.2],[0,0,-1,0]]
    camera=dict(width=size,height=size,projection=projection,position=[0,1.25,0],orientation=[0,0,0])
    return dict(rgb=dict(camera),depth=dict(camera,near=0.,far=10.),
                execution=dict(forward_step_m=.25,turn_degrees=15.,max_episode_steps=500))

class Runtime:
    def __init__(self,config):self.updates={};self.count=0
    def reset(self,episode,calibration):self.episode=episode;self.active=True
    def process(self,packet):
        pose=np.eye(4);pose[0,3]=self.count*.01;self.count+=1
        self.updates[packet.frame_id]=dict(episode_id=self.episode,map_version=0,optimized_keyframes={"1":np.eye(4).tolist()})
        return PoseEstimate(self.episode,packet.frame_id,packet.timestamp_ns,T_odom_base=pose,T_map_base=pose,
            valid=True,tracking_state="tracking",source="cuvslam_rtabmap_rgbd",map_version=0,
            rtab_keyframe_id=1,T_keyframe_base=pose,diagnostics={"measurement_support":{"kind":2,"used":1,"prediction_used":False}})
    def map_update_for_frame(self,frame):return self.updates[frame]
    def status(self):return dict(active=self.active,reference_registration_available=True,measurement_support_available=True)
    def shutdown(self):self.active=False

def adapter_factory(config,options):return PoseAdapter(config,options,native_factory=Runtime)
