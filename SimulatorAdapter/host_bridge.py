"""Pose-only RPC across Habitat VectorEnv. All simulator access remains in this package."""
import hashlib,json,os,uuid
from pathlib import Path
from functools import lru_cache
import numpy as np
from .pose import SimulatorAdapter,InvalidSimulatorMeasurement,simulator_base_transform
from graphAdapter.interfaces.pose import PoseSessionChanged
from poseAdapter.coordinate.transforms import checked_transform

def profile_identity(profile):
    from graphAdapter.interfaces.pose.policy import require_simulator_profile
    if not isinstance(profile,dict):raise PermissionError('Pose RPC profile must be an object')
    try:require_simulator_profile(profile)
    except ValueError as error:raise PermissionError(str(error)) from error
    return hashlib.sha256(json.dumps(profile,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

class _PoseProfileRejected(PermissionError):
    pass


def _file_version(stat):
    return stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns


@lru_cache(maxsize=1)
def _profile_file_identity(path,version):
    """Cache only a validated digest. Bind cold reads to one filesystem revision."""
    with path.open('rb') as stream:
        if _file_version(os.fstat(stream.fileno()))!=version:
            raise PermissionError('Pose RPC profile changed before read')
        digest=profile_identity(json.load(stream))
        if _file_version(os.fstat(stream.fileno()))!=version:
            raise PermissionError('Pose RPC profile changed during read')
    return digest


def invalidate_pose_binding(environment):
    """A Habitat reset can reuse both the episode instance and its registry member."""
    environment._graph_pose_binding = None
    environment._graph_pose_generation += 1


def read_pose_state(environment,*,expected_episode_uid,profile_sha256,pose_session):
    from case1_runtime.observations import graph_hook_enabled
    if not graph_hook_enabled(os.environ):raise _PoseProfileRejected('Simulator pose hook is disabled')
    path=os.environ.get('CASE2_POSE_PROFILE')
    if not path:raise _PoseProfileRejected('No simulator pose diagnostic profile')
    path=Path(path)
    try:
        digest=_profile_file_identity(path,_file_version(path.stat()))
    except FileNotFoundError:
        raise
    except (OSError,ValueError) as error:
        raise _PoseProfileRejected('Cannot validate simulator pose profile') from error
    if digest!=profile_sha256:raise _PoseProfileRejected('Pose RPC profile differs from host')
    from case1_runtime.episode_scope import episode_scope
    episode=environment._env.current_episode
    current=episode_scope(episode)['episode_uid']
    if current!=expected_episode_uid:raise PoseSessionChanged('Pose RPC episode differs from captured observation')
    if not hasattr(environment,'_graph_pose_generation'):
        environment._graph_pose_generation=0
    generation=environment._graph_pose_generation
    binding=getattr(environment,'_graph_pose_binding',None)
    if pose_session is not None and (binding is None or binding[0]!=pose_session or binding[1] is not episode):
        raise PoseSessionChanged('Pose RPC belongs to an expired simulator session')
    state=environment._env.sim.get_agent_state(0)
    after=environment._env.current_episode
    if (after is not episode or episode_scope(after)['episode_uid']!=current
            or environment._graph_pose_generation!=generation or getattr(environment,'_graph_pose_binding',None) is not binding):
        raise PoseSessionChanged('Simulator episode changed during pose read')
    world_base=simulator_base_transform(state)
    if pose_session is None:
        token=uuid.uuid4().hex
        # The world origin is private to this environment and invalidated on reset.
        environment._graph_pose_binding=(token,episode,np.linalg.inv(world_base))
        return dict(episode_uid=current,pose_session=token,T_episode_base=np.eye(4).tolist())
    relative=checked_transform(binding[2]@world_base)
    return dict(episode_uid=current,T_episode_base=relative.tolist())

def pose_rpc_reply(environment,*,expected_episode_uid,profile_sha256,pose_session):
    """Return only pose values and private session identity across the VectorEnv boundary."""
    try:
        return read_pose_state(environment,expected_episode_uid=expected_episode_uid,profile_sha256=profile_sha256,pose_session=pose_session)
    except PoseSessionChanged:
        return dict(episode_uid=expected_episode_uid,pose_error='session_changed')
    except InvalidSimulatorMeasurement:
        return dict(episode_uid=expected_episode_uid,pose_error='invalid_measurement')
    except (_PoseProfileRejected,FileNotFoundError):
        return dict(episode_uid=expected_episode_uid,pose_error='profile_rejected')


class _VectorPoseSource:
    def __init__(self,envs,index,digest):self.envs=envs;self.index=index;self.digest=digest;self.episode=None;self.session=None
    def read_pose(self):
        if self.episode is None:raise ValueError('Bound single-agent episode required')
        row=self.envs.call_at(self.index,'graph_pose_state',dict(expected_episode_uid=self.episode,profile_sha256=self.digest,pose_session=self.session))
        if not isinstance(row,dict) or row.get('episode_uid')!=self.episode:
            raise PoseSessionChanged('Pose RPC reply does not identify the bound episode')
        if set(row)=={'episode_uid','pose_error'}:
            if row['pose_error']=='invalid_measurement':raise InvalidSimulatorMeasurement('Invalid simulator pose measurement')
            if row['pose_error']=='session_changed':raise PoseSessionChanged('Pose RPC episode changed during capture')
            if row['pose_error']=='profile_rejected':raise PermissionError('Pose RPC profile rejected')
        expected={'episode_uid','T_episode_base'}
        if self.session is None:
            expected.add('pose_session')
            token=row.get('pose_session')
            if not isinstance(token,str) or len(token)!=32 or any(c not in '0123456789abcdef' for c in token):
                raise PoseSessionChanged('Invalid simulator session receipt')
        if set(row)!=expected:
            raise PoseSessionChanged('Unexpected schema in bound pose RPC')
        try:
            raw=np.asarray(row['T_episode_base'])
            if raw.dtype.kind not in 'fiu':raise ValueError('Numeric transform required')
            measured=checked_transform(raw)
        except (TypeError,ValueError,OverflowError) as error:
            raise PoseSessionChanged('Invalid episode transform in pose RPC') from error
        if self.session is None:
            if not np.array_equal(measured,np.eye(4)):
                raise PoseSessionChanged('Simulator reset did not establish a local origin')
            self.session=token
        return measured

class _VectorPoseAdapter(SimulatorAdapter):
    def __init__(self,source):
        self._pose_rpc=source
        self.agent_id=0
        self._init_pose_reader(source.read_pose)
    def reset_episode(self,episode_id,*,calibration=None,depth_spec=None):
        with self._lock:
            if self.closed:
                raise RuntimeError('SimulatorAdapter is closed')
            previous=(self._pose_rpc.episode,self._pose_rpc.session)
            self._pose_rpc.episode,self._pose_rpc.session=episode_id,None
            try:
                return super().reset_episode(episode_id,calibration=calibration,depth_spec=depth_spec)
            except BaseException:
                self._pose_rpc.episode,self._pose_rpc.session=previous
                raise
    def shutdown(self):
        super().shutdown();self._pose_rpc=None

def make_vector_factory(envs,profile,*,env_index=0):
    digest=profile_identity(profile)
    def factory(input_config,options):
        return _VectorPoseAdapter(_VectorPoseSource(envs,env_index,digest))
    return factory
