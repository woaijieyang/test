# Unified pose interface contract

This directory owns the provider-neutral interface and chart-continuity semantics.
Implementation acquisition remains in `src/poseAdapter/` or `src/SimulatorAdapter/`.
GraphAdapter receives serializable pose DTOs; it does not receive simulator handles.

## Input and output

`PoseProvider.reset_episode(episode_id, calibration=..., depth_spec=...)` starts a new
session. A repeated episode name still creates a distinct `episode_instance`.
`PoseReader.capture(episode_id, frame_id, timestamp_ns, **observations)` checks the
session before and after acquisition. `read(...)` requests an exact historical
frame. Identity, timestamp, provider and version mismatches fail explicitly.

`PoseFrame` schema 1 contains exactly source, episode_id, episode_instance,
frame_id, timestamp_ns, map_version, valid, T_map_base, T_odom_base, T_map_odom
and schema_version. Matrices are immutable numeric 4x4 rigid transforms, column
vectors, meters, FLU base convention. Invalid poses contain no geometry. Camera
pose is derived from this pose and the existing static camera extrinsic in the
observation boundary, not from simulator sensor-state truth.

## Provider capabilities are explicit

| Aspect | Native PoseAdapter | Temporary SimulatorAdapter |
|---|---|---|
| source | cuvslam_rtabmap_rgbd | simulator_ground_truth |
| input needed for estimation | Actual RGB-D and calibration | Pose-only API position/rotation |
| base odometry | Original native measured odometry | Episode-initial exact pose chart |
| map pose | Original mapping correction | Same as odometry |
| map version | Native published version | 0 for the entire session |
| measurement validity | Original measured support checks | Validated pose response and frame/session identity |
| correction/recovery | Original native APIs and gating | No native correction, recovery or keyframes are fabricated |
| closure | Native owner shutdown | Release adapter readers/cache; never close the host-owned simulator |

A source enum is mandatory. The execution entrypoint requires explicit Simulator configuration for planned
stages 000 through 006. It rejects native or unspecified providers instead of
automatically falling back. Only a later explicit user arrangement may change
this policy. Stage permission does not implement or enable later-stage features.

## Continuous odometry and execution edges

`continuous_odometry_chart(previous, current)` returns `(chart_id, None)` or
`(None, reason)`. Callers first validate measured pose DTOs. Native behavior
retains verified global-frame epoch plus unchanged odometry-frame-link checks.
Simulator mode requires a matching nonempty episode session and unchanged zero
map version. No native SLAM diagnostics are fabricated for simulator mode.

Chart continuity alone does not establish a traversed edge. GraphAdapter also
requires consecutive recorded endpoints, an actual forward primitive, explicit
no-collision feedback, and plausible measured base translation. Turns,
collisions, missing feedback, reset/session changes and implausible jumps do not
create traversed edges. Such edges mean only recorded forward traversal, never
current reachability, reverse reachability or a straight-line shortcut.

## Isolation

Simulator truth acquisition, simulator API compatibility and their tests stay
under `src/SimulatorAdapter/`. The RPC allowlist is episode_uid, position and
rotation_wxyz. The shared interface imports no Habitat APIs. The private memory
worker cannot import SimulatorAdapter. RGB-D, calibration, timestamps and action
feedback retain their original observation/execution channels. No goal pose,
semantic labels, object IDs, navmesh, path distance or evaluation metrics are
allowed in the pose DTO or graph-memory input.

## Validation evidence

- `review/traversed-repair/REVIEW.json`: change scope and native regression.
- `review/traversed-repair/REAL_PACKET_REPLAY.json`: before/after real endpoint data.
- `review/traversed-repair/PUBLIC_READER_NEGATIVE_CONTROL.json`: independently
  detects missing edges in the old sealed map after public-reader reload.
- `simulator-quality80-traversed-v2/control/SUPERVISOR_PROGRESS.json`: ongoing
  online validation, not a completed acceptance receipt.

The native PoseAdapter implementation and configuration were preserved.


模拟器端点会话在 PoseBridge.reset 成功后绑定到 MappingSessionIdentity。统一调用方可通过 PoseReader.capture/read 的 expected_instance 校验会话；SimulatorAdapter 的条件采集在同一把锁内校验身份并写入帧缓存。PoseSessionChanged 表示当前桥接器已经失去原会话，宿主封存未提交的失败端点。单帧测量不可用时仍保留同一次会话的 RGB-D 证据与 unavailable 位姿，后续正常端点可以继续。单帧 DTO 不包含模拟器实例或传感器句柄。
