# Published map reader contract

Implementation: store.py SnapshotReader and pages.py FactMaterializer.
This documents the existing stage001 API; it does not enable model injection.

## Pinning and lifetime

Use load_episode(root, revision='CURRENT') once per read transaction. The reader
pins a concrete snapshot_id, versions and cutoff; later publications do not
change that handle. Close it in finally. Do not mix live dictionaries, SQL latest
rows, or values read through separate snapshots into a single evidence bundle.
An explicit requested revision must belong to the committed ancestry.

## Views and images

get_view(frame_uid, include_images=True, include_depth=False) returns immutable
metadata/arrays. frame_uid, capture_seq, snapshot_id and pose_map_version identify
what was actually observed and which published geometry interprets it.

- raw_rgb: decoded RGB evidence, available when include_images is true.
- host_view: the separately recorded host image after its declared observation
  transform. This is not interchangeable with raw_rgb merely because shapes match.
- raw_rgb_ref and host_view_ref: owned references, containing path/hash/bytes,
  resolved and verified relative to this map root by the reader.
- capture: immutable acquisition provenance, including original identities,
  calibration, capture-time pose and old capture paths.
- capture.raw_rgb_ref/raw_depth_ref/aligned_ref are historic acquisition paths.
  They may intentionally no longer exist after work-cache cleanup. They are not
  the authoritative post-retention loading addresses. Use reader materialization
  or owned references, never reconstruct paths into deleted work directories.
- depth: requested explicitly; raw/aligned arrays and valid masks retain their
  declared calibration and dimensions. Do not silently resize independently in
  geometry and object consumers.

Do not compare a stored-file checksum with the decoded pixel hash or normalized
model tensor hash. Those identify different representations. Future model-input
compilation must preserve raw -> host transform -> processor tensor provenance.
Do not feed visualization images into the baseline's original image slots.

## Objects, aliases and class evidence

get_object(epoch, native_id) resolves aliases in the pinned snapshot. Retired and
ambiguous identities remain explicit. Never replace a missing identity with a
same-name object or assume the same numeric ID across epochs is the same object.

get_object_evidence(epoch, native_id, frame_uid=None, detection_index=None)
returns exact original detection members. Each source binds frame_uid,
detection_index, source_class_id, confidence, original_box, crop_box, crop,
raw_rgb_ref and raw_depth_ref. A source crop uses that member's original box,
not an aggregate object box or a box copied from another frame. Supplying a
detection_index requires frame_uid. Invalid/empty boxes return an explicit
unavailable crop, not an invented replacement.

Aggregate class_name is a model vote, not a verified physical identity. Check
identity_scope, all_object_source_class_ids, class_evidence, ambiguities and
single_physical_object_verified. Filtering to one source does not erase the
whole object's known class conflicts. Room-type hints are soft CLIP labels,
not room instances or confirmed floor IDs. These uncertainty fields do not
require a perfect detector; they prevent consumers from overstating evidence.

## Geometry and execution

get_geometry(tile_id, revision=...) requires the same pinned revision. It returns
owner-core arrays with explicit coordinate metadata. free_count and
surface_count are independent sensor evidence. Their overlap is a conflict;
absence of both is unknown. A displayed free cell is not certified traversability.

get_trace(start, end) returns actual recorded endpoint transitions.
temporal_next means ordered observation, including turns/collisions/STOP.
traversed additionally requires measured same-chart base translation supported
by an actual forward action and no-collision feedback. It is directed recorded
traversal, not a reverse edge, current passability or geometric shortcut.

## Failure handling and retention

Unknown frames, missing source members, checksum mismatch and snapshot mismatch
are explicit failures. Never substitute another episode or visually similar
image. An unavailable spatial field may still leave valid visual evidence.
Final retained maps keep their referenced images/depth/object/geometry material;
compute work is deleted only after independent cold-reader verification.
Classification uncertainty is not an archive integrity failure.

## Diagnostic snapshot ownership

Do not hardlink live producer files into diagnostic or benchmark directories.
Even read-only use changes st_nlink/ctime and violates lifecycle ownership checks.
Use a read-only SQLite backup plus independent copies (or verified reflinks with
separate inodes), while pinning the selected committed revision. Copy immutable
observations, detections and blobs required by the selected history, not only the
current manifest. Keep the snapshot pointer and schema identity exact. Release
reader pins promptly. Diagnostic files must have independent ownership and must
never cause production cleanup to remove or retain another tree unexpectedly.
