"""Check asynchronous completion identity without confusing enqueue with commit.

This validates the owned worker's commit reply. It does not independently prove
filesystem durability; that remains the publisher and pinned-reader contract.
"""
import re
from collections.abc import Mapping


def validated_completion(packet, reply):
    source=packet.to_record() if hasattr(packet,"to_record") else packet
    if not isinstance(source,Mapping) or not isinstance(reply,Mapping):
        raise ValueError("Observation and commit receipt mappings required")
    if reply.get("duplicate") is True:
        raise ValueError("Duplicate completion requires explicit recovery, not a new publication")
    uid=source["frame_uid"];episode=source["episode_uid"]
    if not isinstance(uid,str) or not uid.startswith(episode+":"):
        raise ValueError("Observation identity is not in its episode")
    if "episode_uid" in reply and reply["episode_uid"]!=episode:
        raise ValueError("Completion belongs to another episode")
    if (reply.get("frame_uid")!=uid or type(reply.get("source_packet_event_seq")) is not int
            or reply["source_packet_event_seq"]!=source["event_seq"]):
        raise ValueError("Completion belongs to another source observation")
    sid=reply.get("snapshot_id")
    if not isinstance(sid,str) or re.fullmatch(r"[0-9a-f]{64}",sid) is None:
        raise ValueError("Committed content-addressed snapshot identity required")
    cutoff=reply.get("cutoff")
    if not isinstance(cutoff,Mapping) or any(type(cutoff.get(k))is not int or cutoff[k]!=source[k]
                                          for k in ("capture_seq","event_seq")):
        raise ValueError("Completion cutoff differs from admitted observation")
    versions=reply.get("versions")
    if not isinstance(versions,Mapping) or "pose_map_version" not in versions:
        raise ValueError("Published version contract missing")
    version=versions["pose_map_version"]
    if version is None and source.get("pose_record",{}).get("geometry_status")=="available":
        raise ValueError("Measured geometry cannot publish without a pose revision")
    if version is not None and (type(version)is not int or version<0):
        raise ValueError("Published pose revision is invalid")
    # Return a private JSON-shaped copy: the caller/worker cannot later mutate
    # a completion that the host is about to publish in its ordered event log.
    import json
    return json.loads(json.dumps(dict(reply),allow_nan=False))
