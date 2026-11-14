"""Strict indexing for endpoint and correction-only map publications."""
def index_publications(flow,packets):
    endpoint={}
    revisions={}
    for event in flow:
        kind=event.get("kind")
        if kind not in ("PublishedSnapshot","MapCorrectionPublished"):
            continue
        uid=event.get("frame_uid")
        packet=packets.get(uid)
        if packet is None or event.get("source_packet_event_seq")!=packet["event_seq"]:
            raise ValueError("Map publication source identity mismatch")
        if event.get("cutoff_event_seq")!=packet["event_seq"]:
            raise ValueError("Map publication cutoff differs from its source")
        if kind=="PublishedSnapshot":
            if uid in endpoint:raise ValueError("Duplicate endpoint publication")
            endpoint[uid]=event
        elif uid not in endpoint:
            raise ValueError("Correction publication precedes its endpoint")
        sid=event["snapshot_id"]
        if sid in revisions:raise ValueError("Duplicate snapshot publication")
        revisions[sid]=event
    return endpoint,revisions
