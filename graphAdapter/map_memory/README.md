# Stage001: recoverable geometry and visual-semantic memory

This package consumes committed000ObservationPackets. It does not append memory to
the navigation model,call a planner,obtain additional observations or read GT.
The independent poseAdapter0.1.3 remains the same43-source-file installed release.

| Functional owner | Implementation | Contract |
|---|---|---|
| Geometry | geometry/core.py | Source TSDF arithmetic,explicit free/surface evidence,fixed tiles and unique owner cores |
| Perception | perception/scene.py | Original YOLO-World/SAM/OpenCLIP and CG association,clustering,anchors,aliases,local camera facts |
| Raw/archive compatibility | storage/archive.py | One raw fact/array codec implementation and legacy read-only snapshots |
| Persistent index/materialization | storage/pages.py | Content-addressed pages,verified child index,immutable raw materializer and byte-bounded caches |
| Public storage API | storage/store.py | One active writer,pinned readers,history audit,incremental accounting and one atomic CURRENT |
| Endpoint/correction | service.py | Same-frame000receipt verification,per-keyframe correction,prepare/grant/commit,rollback/reload |
| Deployment | worker.py | Lightweight parent,owned broker/RPC,private model worker,explicit resource and shutdown contracts |
| Inspection | visualization.py | Readonly estimated3D point cloud and explicit height slice;floor_id remains null |
| Validation | validation.py and tests/ | Named component assertions;CPU status does not grant navigation readiness |
| Navigation evaluation | ../evaluation/ | Existing Aware host,sealedA order,genuine nohook control,source/input/behavior/cost audits |

## Data flow

1. The000hook archives raw RGB-D,calibration and aligned depth/mask,then commits
   its packet to both logs. The resulting immutable receipt binds frame/episode,
   event ordinal,calibration and all sensor hashes.
2. The private worker verifies that exact receipt and original endpoint paths.
   It archives source facts before preparing derived state. Invalid original
   poses stay visual-only;later corrections never turn them into valid captures.
3. Detection/SAM/CLIP facts are saved in camera coordinates before world fusion.
   Original association,merge,cleanup and anchor/clustering run in source order.
4. Pose corrections resolve each capture through its own public keyframe binding.
   If any historical full camera/base matrix changes,replay every contribution
   into a fresh candidate. An opt-in exact reuse path compares every matrix with
   np.array_equal;it only reuses unchanged historical facts. Every changed pose
   revision receives a new entity epoch,including exact-reuse revisions.
5. A parent public-pose check grants a candidate hash/version. Raw facts and
   candidate revision pages are durable before the final CURRENT replacement.
   Candidate SQL rows alone never grant visibility. Pre-CURRENT failures leave
   the prior snapshot pinned;post-CURRENT errors reload the committed state.
6. Reload verifies snapshot identity,hashes and references. Geometry access needs
   a pinned snapshot. Check reader.require_pose_version(episode_uid,map_version)
   before spatial comparisons;unsupported versions are unavailable.

## Storage and lifecycle

The public entry remains storage.store.EpisodeStore/load_episode. Schema2 keeps
facts,execution records,current geometry and literal historical object/alias maps
under one signed persistent root. Changes rewrite only the affected history-map
paths;old values are not reinterpreted when pose context changes. Ordinary reads
look up pinned keys;forced cold verification and streamed iter_verified_history
check complete published ancestry,shared pages and original file references.
Legacy schema1 snapshots are read-only. Use the API/CLI instead of assuming
revisions/graph.json files exist in the current format.

The page/file/materialization cache has one owner in storage.pages. Cache byte
limits are not a bound on a fully loaded logical graph or whole process RAM.
Reader pins and every published ancestor protect referenced data. GC checks
revision/page/child identities before removing only unreachable metadata pages;
raw sensor material and referenced blobs are retained.

The worker releases endpoint preparation and episode-end locals at their request
boundaries. Normal and aborted episode bytes remain charged. End/abort receipts
separate current RSS/USS/fds,process-lifetime peaks,allocator allocated/reserved
bytes and process I/O counters. Fixed models stay loaded between episodes;model
process shutdown is checked before changing domains. A worker-output budget is
not a global paired-run quota.

## Coordinates and source adaptations

The000internal map is FLU Z-up. At this package boundary,Q converts it once to
estimated Y-up G. Object backprojection uses T_G_cv@diag(1,-1,-1,1) and
cy_up=H-1-cy_cv. TSDF uses A@inverse(T_G_L)@T_G_cv. No GT gauge or scene bounds
are used. Depth registration remains000-owned.

The original TSDF free/explore arithmetic is retained;unknown negative initial
values are not walls. Surface/free evidence is explicit. Only owner cores are
published;halo samples do not double-count or turn invalid indices into borders.

The original ViewRecord random display color is replaced by a deterministic
frame-identity color;association does not read it. The original pure PIL crop
resize is retained locally to avoid importing its simulator-owning source module.
Candidate forks also copy mutable clustering state. No detector/association
threshold or action/parser/STOP budget is changed.

## Deployment and validation status

Authoritative workflow: docs/specs/graphAdapter-8d4e1845-6SDQEX/graphAdapter_execution/docs/001_geometry_graph.md,
with006stages1-3. Evidence is server-side under
outputs/graph_memory/graph001-20261107-r0.

The profile implementation_status is the gate. Pending means CLI eval refuses
navigation. Recorded pipeline/RPC results are not navigation results. The current
version has separate CPU,recorded-material and native qualification evidence.
The module passed122 CPU contracts,all501 existing logical states and published
histories,and a short real-weight end/abort/serial/cross-domain lifecycle check.
The previous r1 source passed32 paired smoke members;that is not a result for
this changed source or the disjoint presealed random32 selection. A new common
source/control/shadow run is required. FullA612/407 and002 await separate review;
neither is automatically authorized by these qualification results.

Commands run through scripts/with_runtime.sh;the CLI can inspect/render only
published server episode paths. Use the private memory Python with-I for its
dependencies;host evaluation uses the existing Aware Python. The broker mounts
only observation_pose as input and the new memory output as writable state.
Annotations,main model weights and evaluator_private are absent in the worker.

All attempts,failed checks and superseded source receipts remain evidence.
They are not alternative active implementations. Only this src package and its
named profile are active;do not import diagnostic scripts or source tarballs.
