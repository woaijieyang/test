"""Execution facts are reserved before clock checks; raw archives are exclusive."""
import json,re,os
from pathlib import Path
import numpy as np
from .alignment import array_hash

class Coordinator:
    def __init__(self,output,*,storage=None):
        self.root=Path(output);self.root.mkdir(parents=True,exist_ok=False)
        self.storage=storage;self.storage_episode=None
        self.stream=None if storage is not None else(self.root/"flow_trace.jsonl").open("x")
        self.event_seq=0;self.episode_uid=None;self.pending_endpoint=None

    def emit(self,kind,**fields):
        sequence=self.event_seq+1
        row=dict(kind=kind,event_seq=sequence,episode_uid=self.episode_uid,**fields)
        self.stream.write(json.dumps(row,allow_nan=False)+"\n");self.stream.flush()
        self.event_seq=sequence
        return row

    def reset(self,episode_uid,*,identity=None):
        if not isinstance(episode_uid,str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*",episode_uid):
            raise ValueError("Episode UID must be one safe path segment")
        if self.episode_uid is not None:raise RuntimeError("Previous episode not terminated")
        if self.storage is not None:
            if identity is None:raise ValueError('Production storage needs full episode identity')
            self.storage_episode=self.storage.episode(identity)
            folder=self.storage.register(self.storage_episode,'source000',self.root/episode_uid,'source000/'+episode_uid)
            self.storage.session(self.storage_episode,'source000')
            self.stream=(folder/'flow_trace.jsonl').open('x')
        self.episode_uid=episode_uid;self.capture_seq=self.env_step=self.decision_id=0
        self.frame_uid=None;self.last_timestamp=self.last_capture_monotonic_ns=-1;self.pending_endpoint=None
        self.emit("reset",identity=identity)

    def capture(self,rgb,depth,timestamp_ns,*,action_id=None,terminal=False,macro_id=None,
                primitive_index=None,primitive_count=None,collision=None,capture_monotonic_ns=None,
                capture_clock_source="endpoint",received_monotonic_ns=None):
        if self.episode_uid is None:raise RuntimeError("No active episode")
        if action_id is not None:self.env_step+=1
        self.capture_seq+=1
        self.frame_uid=f"{self.episode_uid}:f{self.capture_seq:06d}"
        clock_errors=[]
        if type(timestamp_ns)is not int or timestamp_ns<=self.last_timestamp:
            clock_errors.append(dict(clock="sensor_timestamp_ns",raw_value=timestamp_ns,
                previous_valid_value=self.last_timestamp,error="Nonmonotonic sensor clock"))
        else:self.last_timestamp=timestamp_ns
        if capture_monotonic_ns is None:
            clock_errors.append(dict(clock="capture_monotonic_ns",raw_value=None,
                previous_valid_value=self.last_capture_monotonic_ns,error="Missing acquisition clock"))
        elif type(capture_monotonic_ns)is not int or capture_monotonic_ns<=self.last_capture_monotonic_ns:
            clock_errors.append(dict(clock="capture_monotonic_ns",raw_value=capture_monotonic_ns,
                previous_valid_value=self.last_capture_monotonic_ns,error="Nonmonotonic wall acquisition clock"))
        else:self.last_capture_monotonic_ns=capture_monotonic_ns
        record=dict(frame_uid=self.frame_uid,env_step=self.env_step,capture_seq=self.capture_seq,
            sensor_timestamp_ns=timestamp_ns,capture_monotonic_ns=capture_monotonic_ns,
            capture_clock_source=capture_clock_source,received_monotonic_ns=received_monotonic_ns,
            decision_id=self.decision_id or None,raw_rgb_ref=None,raw_depth_ref=None,
            rgb_hash=None,depth_hash=None,archive_errors=[],archive_failed=False,clock_errors=clock_errors,
            partial_files=[],action_id=action_id,terminal=terminal,macro_id=macro_id,
            primitive_index=primitive_index,primitive_count=primitive_count,collision=collision)
        self.pending_endpoint=record
        folder=self.root/self.episode_uid/f"f{self.capture_seq:06d}"
        owned=False
        try:
            folder.mkdir(parents=True,exist_ok=False);owned=True
        except Exception as error:
            record["archive_failed"]=True
            record["archive_errors"].append(dict(stage="archive_directory",error=type(error).__name__+": "+str(error)))
        if owned:
            for name,value in (("rgb",rgb),("depth",depth)):
                if value is None:
                    record["archive_errors"].append(dict(stage="raw_"+name,error="unavailable"));continue
                path=folder/(name+".npy")
                try:
                    array=np.asarray(value)
                    if array.dtype.hasobject:raise TypeError("Raw sensor array cannot contain Python objects")
                    # Never truncate a previous or partially written archive.
                    with path.open("xb") as stream:
                        np.save(stream,array,allow_pickle=False);stream.flush();os.fsync(stream.fileno())
                    record["raw_"+name+"_ref"]=str(path);record[name+"_hash"]=array_hash(array)
                except Exception as error:
                    record["archive_failed"]=True
                    record["archive_errors"].append(dict(stage="raw_"+name,error=type(error).__name__+": "+str(error)))
                    if path.exists():record["partial_files"].append(str(path))
        return self.emit("raw_archive",**record)

    def decision(self):
        if self.frame_uid is None:raise RuntimeError("Decision before first capture")
        self.decision_id+=1
        return self.emit("decision",frame_uid=self.frame_uid,env_step=self.env_step,
                         decision_id=self.decision_id,cutoff_event_seq=self.event_seq)

    def end_episode(self,cancelled_actions=()):
        self.emit("terminal",frame_uid=self.frame_uid,env_step=self.env_step,cancelled_actions=list(cancelled_actions))
        self.episode_uid=None

    def close(self):
        if self.episode_uid is not None:raise RuntimeError("Episode still active")
        if self.stream is not None:self.stream.close()
