"""Auditable compatibility, reset and evidence patches; parser/policy unchanged."""

import difflib, json
from workspace import ROOT, atomic_json, digest


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError("Unexpected upstream source shape: " + old[:70])
    return text.replace(old, new, 1)


def main():
    changes = []

    def patch(rel, fn):
        path = ROOT / rel
        before = path.read_text()
        after = fn(before)
        if after == before:
            raise RuntimeError("No change: " + rel)
        diff = "".join(
            difflib.unified_diff(
                before.splitlines(True),
                after.splitlines(True),
                fromfile="a/" + rel,
                tofile="b/" + rel,
            )
        )
        (
            ROOT / "patches" / (str(len(changes) + 1).zfill(2) + "-" + path.name + ".patch")
        ).write_text(diff)
        oldhash = digest(path)
        path.write_text(after)
        changes.append({"path": rel, "before_sha256": oldhash, "after_sha256": digest(path)})

    def registry(text):
        return replace_once(
            text,
            'for _model_type in ("awarevln_llama", "llava_llama", "onetwovla_navid_llama"):\n    AutoConfig.register(_model_type, LlavaLlamaConfig)',
            """_CONFIG_CLASS_ALIASES = {LlavaLlamaConfig.model_type: LlavaLlamaConfig}
for _model_type in ("llava_llama", "onetwovla_navid_llama"):
    _config_class = type(_model_type.title().replace("_", "") + "Config", (LlavaLlamaConfig,), {"model_type": _model_type})
    _CONFIG_CLASS_ALIASES[_model_type] = _config_class
for _model_type, _config_class in _CONFIG_CLASS_ALIASES.items():
    AutoConfig.register(_model_type, _config_class)""",
        )

    patch("src/llava/model/language_model/llava_llama.py", registry)

    def trainer(text):
        text = replace_once(
            text,
            "import copy\n",
            "import copy\nimport random\nfrom case1_runtime.trace import TraceRecorder\n",
        )
        text = replace_once(
            text,
            "        model = model.cuda()\n",
            "        model = model.cuda()\n        TraceRecorder.model_loaded(checkpoint_path, tokenizer, model)\n",
        )
        text = replace_once(
            text,
            "        observations = envs.reset()\n",
            """        random.seed(config.TASK_CONFIG.SEED)
        np.random.seed(config.TASK_CONFIG.SEED)
        torch.manual_seed(config.TASK_CONFIG.SEED)
        observations = envs.reset()
        recorder = TraceRecorder.from_environment()
        def record_step(actions, stop_source="model"):
            ep = envs.current_episodes()[0]
            before = envs.call_at(0, "case1_evaluator_state")
            recorder.ensure_episode(ep, before)
            outcome = envs.step(actions)
            after = envs.call_at(0, "case1_evaluator_state")
            recorder.step(ep, actions[0], before, after, outcome[0][2], outcome[0][3], stop_source)
            return outcome
""",
        )
        text = replace_once(
            text,
            '        reason_stuck_id_path = os.path.join(config.RESULTS_DIR, "reason_stuck_id.txt")',
            '        TraceRecorder.effective_configuration(config)\n\n        reason_stuck_id_path = os.path.join(config.RESULTS_DIR, "reason_stuck_id.txt")',
        )
        # Replace only original step assignments; the wrapper's underlying call is untouched.

        text = text.replace("outputs = envs.step(", "outputs = record_step(")
        text = replace_once(
            text,
            "outputs = record_step([ACTION_ID_STOP])",
            'outputs = record_step([ACTION_ID_STOP], stop_source="reason_stuck")',
        )
        text = replace_once(
            text,
            "                    outputs = tokenizer.batch_decode(output_ids, skip_special_tokens=False)[0].strip()\n",
            """                    outputs = tokenizer.batch_decode(output_ids, skip_special_tokens=False)[0].strip()
                    raw_decoded_for_trace = outputs
""",
        )
        text = replace_once(
            text,
            "                    with torch.inference_mode():\n",
            """                    recorder.ensure_episode(current_episodes[0], envs.call_at(0, "case1_evaluator_state"))
                    recorded_call_id = recorder.begin_model_call(current_episodes[0], frame_id, prompt, past_and_current_rgbs, input_ids, images_tensor, stop_str, conv.sep2)
                    with torch.inference_mode():
""",
        )
        text = replace_once(
            text,
            "                    is_reasoning_mode = False\n",
            """                    recorder.ensure_episode(current_episodes[0], envs.call_at(0, "case1_evaluator_state"))
                    recorder.finish_model_call(recorded_call_id, output_ids, raw_decoded_for_trace, outputs)
                    is_reasoning_mode = False
""",
        )
        text = replace_once(
            text,
            "                observations[i] = envs.reset_at(i)[0]\n",
            """                queue_actions.clear()
                last_reasoning = ""
                last_reason_step = 0
                frame_id = 0
                reason_stuck_num = 0
                reasoning_context = ""
                raw_output_content = ""
                random.seed(config.TASK_CONFIG.SEED)
                np.random.seed(config.TASK_CONFIG.SEED)
                torch.manual_seed(config.TASK_CONFIG.SEED)
                observations[i] = envs.reset_at(i)[0]
""",
        )
        text = replace_once(
            text, "        envs.close()\n", "        recorder.close()\n        envs.close()\n"
        )
        return text

    patch("src/vlnce_baselines/awarevln_trainer.py", trainer)

    def env(text):
        # Add evaluator-only RPC; never added to observation spaces or model inputs.

        pos = text.index("    def get_reward_range(")
        addition = """    def case1_evaluator_state(self):
        state = self._env.sim.get_agent_state()
        return {"position": state.position.tolist(), "rotation_xyzw": [float(state.rotation.x), float(state.rotation.y), float(state.rotation.z), float(state.rotation.w)], "elapsed_steps": self._env._elapsed_steps, "episode_over": self._env.episode_over, "collided": bool(self._env.sim.previous_step_collided)}

"""
        return text[:pos] + addition + text[pos:]

    patch("src/vlnce_baselines/common/environments.py", env)
    patch("src/habitat_extensions/actions.py",lambda text: text.replace("dtype=np.float,", "dtype=float,"))
    atomic_json(ROOT / "configs/source-patches.json", changes)
    print(json.dumps({"patches": len(changes)}))


if __name__ == "__main__":
    main()
