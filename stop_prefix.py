"""STOP-released immutable text prefixes on the existing GoalAdapter store.

This is a model report protocol, not a physical completion verifier.  The
native trainer owns every observation, clock, queue, reason and environment step.
"""
import copy
import hashlib
import json
from pathlib import Path

from goalAdapter.native_goal_hook import NativeGoalHook
from subtaskAdapter.base.contracts import ContractError


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def native_state_view(values):
    """Keep only state under test, never model tensors/old locals dictionaries."""
    names = ('last_reasoning', 'last_reason_step', 'frame_id', 'reason_stuck_num',
             'queue_actions', 'past_rgbs', 'observations', 'batch')
    return {name: values[name] for name in names}


def native_fingerprint(values):
    """Read native locals; do not retain objects or modify any native state.

    Image histories are identified by list/item identity. Selected image pixel
    hashes are independently recorded by TraceRecorder on every model request.
    Hashing all old pixels on every call would add quadratic observer overhead.
    """
    import random
    import numpy as np
    import torch
    reason = values['last_reasoning']
    history = values['past_rgbs']
    np_state = np.random.get_state()
    np_rng = dict(generator=np_state[0], state_sha256=hashlib.sha256(np_state[1].tobytes()).hexdigest(),
                  position=int(np_state[2]), has_gauss=int(np_state[3]), cached_gaussian=float(np_state[4]))
    state = dict(last_reasoning_sha256=sha(reason), last_reasoning_object=id(reason),
                 last_reason_step=values['last_reason_step'], frame_id=values['frame_id'],
                 reason_stuck_num=values['reason_stuck_num'],
                 queue_object=id(values['queue_actions']), queue=copy.deepcopy(values['queue_actions']),
                 history_object=id(history), history_lists=[id(x) for x in history],
                 history_images=[[id(x) for x in row] for row in history],
                 observations_object=id(values['observations']), batch_object=id(values['batch']),
                 python_rng_sha256=sha(repr(random.getstate())), numpy_rng_sha256=sha(canonical(np_rng)),
                 torch_rng_sha256=hashlib.sha256(torch.random.get_rng_state().numpy().tobytes()).hexdigest())
    if torch.cuda.is_initialized():
        state['cuda_rng_sha256'] = [hashlib.sha256(x.cpu().numpy().tobytes()).hexdigest()
                                    for x in torch.cuda.get_rng_state_all()]
    return dict(sha256=sha(canonical(state)), values=state)


class StopPrefixHook(NativeGoalHook):
    """k is derived from GoalAdapter TODOs, never kept as a second authority."""
    def __init__(self, directory, *, provider, variant, renderer, experiment_id, plan_version=1):
        if variant not in ('H', 'I') or type(plan_version) is not int or plan_version != 1:
            raise ContractError('STOP_PREFIX_CONFIGURATION')
        super().__init__(Path(directory) / 'native-goals', provider=provider, close_environment=lambda: None)
        self.variant = variant
        self.renderer = renderer
        self.experiment_id = experiment_id
        self.plan_version = plan_version
        self.event_path = Path(directory) / 'prefix-events.jsonl'
        self.event_path.parent.mkdir(parents=True, exist_ok=True)
        with self.event_path.open('x', encoding='utf-8'):
            pass
        self.binding = None
        self.completed_calls = set()  # replay guard, not a progress index
        self.last_switch_step = None

    def event(self, kind, **fields):
        with self.event_path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(dict(kind=kind, experiment_id=self.experiment_id, **fields),
                                    ensure_ascii=False, allow_nan=False) + '\n')
            handle.flush()

    def begin(self, episode):
        previous = self.goal
        super().begin(episode)
        if previous is None:
            self.binding = None
            self.completed_calls = set()
            self.last_switch_step = None

    @property
    def k(self):
        state = self.goal.snapshot()['state']
        active = next((i for i, row in enumerate(state['todos']) if row['status'] != 'completed'), None)
        return len(state['todos']) if active is None else active + 1

    @property
    def parts(self):
        return tuple(row['text'] for row in self.goal._rule_assembly['units'])

    @property
    def plan_hash(self):
        return self.goal.snapshot()['state']['assembly_sha256']

    def instruction(self, episode):
        self.begin(episode)
        return self.renderer.render(self.variant, self.goal.task.raw_text, self.parts, self.k)

    def bind(self, call_id, instruction, input_ids, image_refs, env_step_count, fingerprint):
        if self.terminal or self.binding is not None:
            raise ContractError('STOP_PREFIX_REQUEST_INFLIGHT_OR_TERMINAL')
        if type(call_id) is not int or call_id < 1 or call_id in self.completed_calls:
            raise ContractError('STOP_PREFIX_REQUEST_REUSED')
        if instruction != self.renderer.render(self.variant, self.goal.task.raw_text, self.parts, self.k):
            raise ContractError('STOP_PREFIX_RENDER_DRIFT')
        ids = input_ids.detach().cpu().tolist() if hasattr(input_ids, 'detach') else input_ids
        self.binding = dict(episode_key=self.goal.task.task_key, call_id=call_id, k=self.k,
                            plan_hash=self.plan_hash, plan_version=self.plan_version,
                            instruction_text=instruction, instruction_bytes_sha256=sha(instruction),
                            input_ids_sha256=hashlib.sha256(json.dumps(ids, separators=(',', ':')).encode()).hexdigest(),
                            image_refs=copy.deepcopy(image_refs), env_step_count=env_step_count,
                            reason_state_fingerprint=copy.deepcopy(fingerprint))
        self.event('model_binding', **self.binding)

    def finish(self, call_id, *, mode, parsed_action, raw_model_output, normalized_output,
               queue_empty, episode_active, env_step_count, fingerprint, fingerprint_reader=None, expected=None):
        binding = self.binding
        if binding is None or binding['call_id'] != call_id or call_id in self.completed_calls:
            raise ContractError('STOP_PREFIX_NO_FRESH_RESPONSE')
        identity = dict(episode_key=self.goal.task.task_key, k=self.k, plan_hash=self.plan_hash,
                        plan_version=self.plan_version, call_id=call_id)
        if any(binding[name] != value for name, value in identity.items()):
            raise ContractError('STOP_PREFIX_STALE_BINDING')
        if expected is not None and any(identity.get(name) != value for name, value in expected.items()):
            raise ContractError('STOP_PREFIX_EVENT_IDENTITY')
        if type(queue_empty) is not bool or type(episode_active) is not bool:
            raise ContractError('STOP_PREFIX_EVENT_FLAGS')
        if mode not in ('REASON', 'ACT') or (mode == 'REASON' and parsed_action is not None):
            raise ContractError('STOP_PREFIX_NATIVE_MODE')
        if env_step_count != binding['env_step_count']:
            raise ContractError('STOP_PREFIX_RESPONSE_AFTER_ENV_STEP')
        origin = 'model_action' if mode == 'ACT' and parsed_action == 0 else None
        intercept = bool(origin and queue_empty and episode_active and not self.terminal and self.k < len(self.parts))
        if intercept:
            before = copy.deepcopy(fingerprint)
            old_k = self.k
            added_hash = sha(self.parts[old_k])
            # Existing native GoalAdapter completion transaction and validator.
            # It changes only GoalAdapter TODOs. No native mutable object is held.
            self._complete(call_id, normalized_output, 'MODEL_ACTION_STOP_LOCAL')
            if self.k != old_k + 1:
                raise ContractError('STOP_PREFIX_NONUNIT_ADVANCE')
            after = fingerprint_reader() if fingerprint_reader is not None else copy.deepcopy(fingerprint)
            if before != after:
                raise ContractError('STOP_PREFIX_HANDOFF_CHANGED_NATIVE_STATE')
            zero = self.last_switch_step == env_step_count
            self.last_switch_step = env_step_count
            self.event('handoff', **binding, old_k=old_k, new_k=self.k,
                       appended_block_sha256=added_hash, actual_environment_action=False,
                       completion_source='model', externally_verified=False,
                       completion_event='model_reported_completion',
                       reason_state_before=before, reason_state_after=after,
                       zero_displacement_consecutive_switch=zero)
        elif origin and episode_active and queue_empty and not self.terminal:
            self.pending_stop = (call_id, normalized_output)
        self.event('model_result', **binding, mode=mode, parsed_action=parsed_action,
                   raw_model_output=raw_model_output, normalized_output=normalized_output,
                   stop_origin=origin, stop_intercepted=intercept,
                   reason_state_at_result=copy.deepcopy(fingerprint))
        self.completed_calls.add(call_id)
        self.binding = None
        return intercept

    def native_step(self, action, done, stop_source, env_step_count):
        origin = 'model_action' if action == 0 and stop_source == 'model' else stop_source if action == 0 else None
        self.event('native_step', episode_key=self.goal.task.task_key, k=self.k,
                   plan_hash=self.plan_hash, plan_version=self.plan_version,
                   call_id=max(self.completed_calls) if self.completed_calls else None,
                   parsed_action=action, stop_origin=origin, stop_intercepted=False,
                   env_step_count=env_step_count, done=bool(done))
        if done:
            self.terminal = True
            # Forced STOP/budget/exception are never completion events.
            if origin == 'model_action' and self.pending_stop is not None and self.k == len(self.parts):
                self._complete(*self.pending_stop, 'MODEL_ACTION_STOP_FINAL_ACK')
            self.goal.close()
            self.goal = None
            self.binding = None

    def abort(self, error):
        if self.goal is not None:
            self.event('abort', episode_key=self.goal.task.task_key, error=repr(error),
                       k=self.k, plan_hash=self.plan_hash, plan_version=self.plan_version,
                       pending_binding=copy.deepcopy(self.binding), goal_state=self.goal.snapshot(),
                       completion_source=None, externally_verified=False)
            self.goal.close()
            self.goal = None
