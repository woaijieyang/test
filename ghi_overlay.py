"""Guarded H/I overlay: external instruction view + parsed ACT STOP hook only."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path

from subtaskAdapter.base.contracts import ContractError, TaskContext
from .stop_prefix import StopPrefixHook, native_fingerprint, native_state_view


def make_overlay(source, *, expected_sha256):
    if hashlib.sha256(source.encode()).hexdigest() != expected_sha256:
        raise ContractError('STOP_PREFIX_BASE_SOURCE_DRIFT')
    original = source
    edits = []
    def change(old, new):
        nonlocal source
        if source.count(old) != 1:
            raise ContractError('STOP_PREFIX_OVERLAY_ANCHOR', old[:100])
        source = source.replace(old, new)
        edits.append((old, new))
    change('@baseline_registry.register_trainer(name="awarevln")',
           '@baseline_registry.register_trainer(name="awarevln_native_language")')
    change('        recorder = TraceRecorder.from_environment()',
           '        recorder = TraceRecorder.from_environment()\n        prefix_hook = case1_prefix_factory()')
    change('            return outcome\n',
           '            prefix_hook.native_step(actions[0], outcome[0][2], stop_source, recorder.steps)\n            return outcome\n')
    change('                    instruction = current_episodes[0].instruction.instruction_text',
           '                    instruction = case1_prefix_instruction(prefix_hook, current_episodes[0], frame_id, past_and_current_rgbs)')
    marker = '                    recorded_call_id = recorder.begin_model_call(current_episodes[0], frame_id, prompt, past_and_current_rgbs, input_ids, images_tensor, stop_str, conv.sep2)'
    change(marker, marker + '\n                    prefix_hook.bind(recorded_call_id, instruction, input_ids, recorder.pending_call["images"], recorder.steps, case1_native_fingerprint(locals()))')
    change('                    if is_reasoning_mode:\n                        last_reasoning',
           '                    if is_reasoning_mode:\n                        prefix_hook.finish(recorded_call_id, mode="REASON", parsed_action=None, raw_model_output=raw_decoded_for_trace, normalized_output=outputs, queue_empty=not queue_actions, episode_active=True, env_step_count=recorder.steps, fingerprint=case1_native_fingerprint(locals()))\n                        last_reasoning')
    marker = '                    if actions[0] == ACTION_ID_FORWARD:'
    change(marker,
           '                    prefix_native_locals = case1_native_view(locals())\n'
           '                    if prefix_hook.finish(recorded_call_id, mode="ACT", parsed_action=actions[0], raw_model_output=raw_decoded_for_trace, normalized_output=outputs, queue_empty=not queue_actions, episode_active=True, env_step_count=recorder.steps, fingerprint=case1_native_fingerprint(prefix_native_locals), fingerprint_reader=lambda: case1_native_fingerprint(prefix_native_locals)):\n'
           '                        continue\n' + marker)
    # No substitutions in native parser/question/queue/REASON/forced STOP. The
    # only new continue is immediately after an accepted local STOP transaction.
    restored = source
    for old, new in reversed(edits):
        if restored.count(new) != 1:
            raise ContractError('STOP_PREFIX_REVERSE_ANCHOR')
        restored = restored.replace(new, old)
    if restored != original or ast.dump(ast.parse(restored)) != ast.dump(ast.parse(original)):
        raise ContractError('STOP_PREFIX_REVERSE_EXACT_FAILED')
    ast.parse(source)
    return source, dict(base_sha256=expected_sha256,
                        overlay_sha256=hashlib.sha256(source.encode()).hexdigest(),
                        reverse_exact=True, substitutions=len(edits),
                        original_file_modified=False, native_question_parser_sampler_generation_unchanged=True,
                        forced_stop_unchanged=True, native_reasoning_and_clock_preserved=True,
                        local_stop_protocol='stop_prefix_v1', navigation_verified=False)


def install(source_path, *, expected_sha256, language_input, snapshot_path, provider, manifest, run_directory):
    root = Path(__file__).resolve().parents[3]
    source_path = Path(source_path).resolve()
    snapshot_path = Path(snapshot_path).resolve()
    run_directory = Path(run_directory).resolve()
    if (not source_path.is_relative_to(root / 'src') or not snapshot_path.is_relative_to(root / 'outputs/subtaskAdapter')
            or not run_directory.is_relative_to(root / 'outputs/subtaskAdapter') or snapshot_path.exists()):
        raise ContractError('STOP_PREFIX_INSTALL_SCOPE')
    if manifest.get('stop_prefix_variant') not in ('H', 'I'):
        raise ContractError('STOP_PREFIX_VARIANT')
    renderer_path = (root / manifest['renderer_file']).resolve()
    if not renderer_path.is_relative_to(root / 'outputs/subtaskAdapter'):
        raise ContractError('STOP_PREFIX_RENDERER_SCOPE')
    renderer_hash = hashlib.sha256(renderer_path.read_bytes()).hexdigest()
    if renderer_hash != manifest['renderer_sha256'] or manifest['files'].get(manifest['renderer_file']) != renderer_hash:
        raise ContractError('STOP_PREFIX_RENDERER_DRIFT')
    spec = importlib.util.spec_from_file_location('case1_frozen_ghi_renderers', renderer_path)
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    if renderer.VERSION != 'ghi-render-v1':
        raise ContractError('STOP_PREFIX_RENDERER_VERSION')
    assemblies = {}
    for key, value in provider.rows.items():
        source = (root / value['source_assembly']).resolve()
        if not source.is_relative_to(root / 'outputs/subtaskAdapter'):
            raise ContractError('STOP_PREFIX_ASSEMBLY_SCOPE')
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != value['assembly_sha256'] or manifest['files'].get(value['source_assembly']) != value['assembly_sha256']:
            raise ContractError('STOP_PREFIX_ASSEMBLY_DRIFT')
        assembly = json.loads(raw)
        if (assembly['task_key'] != key or assembly['raw_instruction'] != value['raw_instruction']
                or [row['text'] for row in assembly['units']] != value['subtasks']
                or hashlib.sha256(''.join(value['subtasks']).encode()).hexdigest() != value['original_E_sha256']):
            raise ContractError('STOP_PREFIX_SOURCE_BINDING')
        initial = renderer.render(manifest['stop_prefix_variant'], value['raw_instruction'], value['subtasks'], 1)
        if initial != value['assigned_task_text']:
            raise ContractError('STOP_PREFIX_INITIAL_RENDER')
        assemblies[key] = assembly
    def assembly_for_episode(ep):
        from case1_runtime.trace import identity
        key = identity(manifest['dataset'], ep)
        a = assemblies[key]
        if ep.instruction.instruction_text != a['raw_instruction']:
            raise ContractError('STOP_PREFIX_EPISODE_ORIGINAL_DRIFT')
        parts = key.split('|')
        return TaskContext(key, parts[0], parts[2], parts[4] if parts[0] == 'r2r' else parts[5],
                           a['raw_instruction'], a['instruction_sha256']), a
    def factory():
        return StopPrefixHook(run_directory, provider=assembly_for_episode,
                              variant=manifest['stop_prefix_variant'], renderer=renderer,
                              experiment_id=manifest.get('experiment_id', run_directory.parent.parent.name),
                              plan_version=manifest.get('plan_version', 1))
    def instruction(hook, ep, frame, images):
        # Existing source/hash/image/phase checks run unchanged. Their immutable
        # source-view receipt is distinct from the actual prefix model binding.
        language_input(ep, frame, images)
        return hook.instruction(ep)
    raw = source_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ContractError('STOP_PREFIX_BASE_SOURCE_DRIFT')
    text, receipt = make_overlay(raw.decode('utf-8'), expected_sha256=expected_sha256)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    with snapshot_path.open('x', encoding='utf-8', newline='\n') as handle:
        handle.write(text)
    spec = importlib.util.spec_from_file_location('case1_stop_prefix_frozen_trainer', snapshot_path)
    module = importlib.util.module_from_spec(spec)
    module.case1_prefix_factory = factory
    module.case1_prefix_instruction = instruction
    module.case1_native_fingerprint = native_fingerprint
    module.case1_native_view = native_state_view
    spec.loader.exec_module(module)
    receipt.update(variant=manifest['stop_prefix_variant'], renderer_sha256=renderer_hash,
                   source_view_binding='input-language-bindings.jsonl (frozen initial view)',
                   actual_model_binding='prefix-events.jsonl (model_binding and model_result)')
    return module, receipt
