"""Legal committed000recordings;never treat an unflushed packet tail as input."""
from pathlib import Path
import json,hashlib
import numpy as np
from graphAdapter.observation_packet import ObservationPacket
from graphAdapter.observation_pose.alignment import RGBDAlignmentBridge,array_hash,verify_aligned_product_archive
from poseAdapter import Calibration,DepthSpec
from graphAdapter.map_memory.storage.store import IntegrityError,canonical

APPROVED000="bef083d830b6a6578e2ffbd8fc1e726a2636c4836e4f5ab27e72d814c372b243"

class CommittedRecording:
    def __init__(self,hook_dir,*,expected_source_sha256=APPROVED000,legacy_alignment_storage=None):
        self.root=Path(hook_dir).resolve();worker=self.root.parent;domain=worker.parent;run=domain.parent
        identity=json.loads((run/"run_identity.json").read_bytes())
        if identity["source_sha256"]!=expected_source_sha256:raise IntegrityError("Recording source identity mismatch")
        status=json.loads((domain/"execution_result.json").read_bytes())
        hook=json.loads((worker/"hook-load.json").read_bytes())
        if status["exit_code"]!=0 or not hook["completed"]or not hook["hook_enabled"]:
            raise IntegrityError("Incomplete or failed source recording")
        if (worker/"attempt-abort.json").exists()or list(self.root.glob("aborted-endpoints/*/attempt-abort.json")):
            raise IntegrityError("Aborted000attempt is not accepted recording material")
        self.source_identity=identity;self.packet_count=hook["packet_count"];self._bridges={}
        if legacy_alignment_storage is None:
            legacy_alignment_storage=expected_source_sha256 in {APPROVED000,'f137ea88e19336ea3822aeeb9da85c6f5227cbdbe223fd77df88bce99f6ffbc3'}
        if type(legacy_alignment_storage)is not bool:raise IntegrityError('Explicit legacy alignment compatibility required')
        self.legacy_alignment_storage=legacy_alignment_storage

    def _bridge(self,episode):
        if episode not in self._bridges:
            cf=json.loads((self.root/episode/"calibration.json").read_bytes())
            cameras={k:Calibration(**{**cf[k],"T_base_camera":np.asarray(cf[k]["T_base_camera"])})for k in ("rgb","depth")}
            bridge=RGBDAlignmentBridge(cameras["rgb"],cameras["depth"],DepthSpec(**cf["depth_spec"]),
                np.linalg.inv(cameras["rgb"].T_base_camera)@cameras["depth"].T_base_camera,invalid_values=(0.,))
            self._bridges[episode]=bridge
        return self._bridges[episode]

    def __iter__(self):
        count=0;event_seq=0;raws={};alignments={}
        with (self.root/"observation-packets.jsonl").open()as packets,(self.root/"flow_trace.jsonl").open()as flow:
            for line in flow:
                event=json.loads(line)
                if event["event_seq"]!=event_seq+1:raise IntegrityError("Nonsequential source event log")
                event_seq=event["event_seq"];kind=event["kind"]
                if kind=="attempt_aborted":raise IntegrityError("Failed source attempt")
                if kind=="raw_archive":raws[event["frame_uid"]]=event
                elif kind=="alignment":alignments[event["frame_uid"]]=event
                elif kind=="observation_packet":
                    packet_data=json.loads(next(packets))
                    if packet_data!=event["packet"]:raise IntegrityError("Packet/flow commit mismatch")
                    packet=ObservationPacket(**packet_data);uid=packet.frame_uid
                    raw=raws.pop(uid)
                    if raw["archive_failed"]or (raw["env_step"],raw["capture_seq"],raw["decision_id"])!=(packet.env_step,packet.capture_seq,packet.decision_id):
                        raise IntegrityError("000archive identity/status differs from packet")
                    alignment=alignments.pop(uid,None)
                    if packet.event_seq!=event_seq or raw["event_seq"]>=packet.event_seq:
                        raise IntegrityError("000commit ordering")
                    count+=1
                    yield packet,raw,alignment
            if next(packets,None)is not None:raise IntegrityError("Uncommitted packet tail")
        if count!=self.packet_count:raise IntegrityError("Packet loading receipt count mismatch")

    def materialize(self,packet,raw,alignment):
        def load(ref):
            if ref is None:return None
            path=Path(ref).resolve()
            expected=self.root/packet.episode_uid/("f"+format(packet.capture_seq,"06d"))
            if path.parent!=expected:raise IntegrityError("Raw material belongs to another endpoint directory")
            return np.load(path,allow_pickle=False)
        rgb=load(packet.raw_rgb_ref);depth=load(packet.raw_depth_ref)
        if (None if rgb is None else array_hash(rgb))!=raw["rgb_hash"]or (None if depth is None else array_hash(depth))!=raw["depth_hash"]:
            raise IntegrityError("Original sensor archive content mismatch")
        aligned=load(packet.aligned_ref);mask=None
        if aligned is not None:
            if alignment is None or array_hash(aligned)!=alignment["aligned_depth_hash"]:
                raise IntegrityError("Aligned archive mismatch")
            recomputed=self._bridge(packet.episode_uid).align(rgb,depth)
            if packet.calibration_hash!=recomputed.calibration_hash:raise IntegrityError("Recording calibration mismatch")
            np.testing.assert_array_equal(aligned,recomputed.depth)
            mask=recomputed.valid_mask
            try:
                storage_verification=verify_aligned_product_archive(Path(packet.aligned_ref).parent,recomputed,alignment,
                    allow_legacy=getattr(self,'legacy_alignment_storage',False))
            except ValueError as error:raise IntegrityError(str(error))from error
        receipt=dict(committed=True,episode_uid=packet.episode_uid,frame_uid=packet.frame_uid,
            capture_seq=packet.capture_seq,env_step=packet.env_step,packet_event_seq=packet.event_seq,
            packet_record_hash=hashlib.sha256(canonical(packet.to_record())).hexdigest(),
            rgb_hash=raw["rgb_hash"],raw_depth_hash=raw["depth_hash"],calibration_hash=packet.calibration_hash,
            alignment=None if aligned is None else dict(aligned_depth_hash=array_hash(aligned),
                valid_mask_hash=hashlib.sha256(np.ascontiguousarray(mask).tobytes()).hexdigest()))
        if aligned is not None:receipt['alignment'].update(storage_verification)
        return dict(rgb=rgb,raw_depth=depth,aligned_depth=aligned,valid_mask=mask,committed_receipt=receipt)
