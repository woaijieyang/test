import copy
import random
from case1_runtime.trace import TraceRecorder
from case1_runtime.observations import policy_observations
from case1_runtime.episode_scope import episode_scope
import datetime
import json
import os
import re
import time

import numpy as np
import torch
import tqdm
from habitat import logger
from habitat.utils.visualizations.utils import append_text_to_image
from habitat_baselines.common.baseline_registry import baseline_registry
from habitat_baselines.common.environments import get_env_class
from habitat_baselines.common.obs_transformers import apply_obs_transforms_batch
from habitat_baselines.common.tensorboard_utils import TensorboardWriter
from habitat_baselines.rl.ddppo.algo.ddp_utils import is_slurm_batch_job
from habitat_baselines.utils.common import batch_obs
from habitat_extensions.utils import observations_to_image
from PIL import Image
from vlnce_baselines.common.base_il_trainer import BaseVLNCETrainer
from vlnce_baselines.common.env_utils import construct_envs_auto_reset_false
from vlnce_baselines.common.utils import extract_instruction_tokens

from llava.constants import IMAGE_TOKEN_INDEX
from llava.conversation import SeparatorStyle, conv_templates
from llava.mm_utils import KeywordsStoppingCriteria, process_images, tokenizer_image_token
from llava.model.builder import load_pretrained_model


def extract_reasoning(llm_output: str) -> str:
    if not llm_output:
        return ""

    reasoning_part = llm_output
    reasoning_part = re.sub(r"(new\s*reasoning\s*is[:\s]*)", "", reasoning_part, flags=re.IGNORECASE)
    reasoning_part = re.sub(r"\[?ph_reasoning_token_?\]?", "", reasoning_part, flags=re.IGNORECASE)
    reasoning_part = re.sub(r"<\|?end_of_text\|?>", "", reasoning_part, flags=re.IGNORECASE)
    reasoning_part = re.sub(r"<begin_of_reasoning>", "", reasoning_part, flags=re.IGNORECASE)
    reasoning_part = re.sub(r"<begin_of_action>", "", reasoning_part, flags=re.IGNORECASE)
    reasoning_part = re.sub(r"<end_of_reasoning>", "", reasoning_part, flags=re.IGNORECASE)
    return reasoning_part.strip(" '\"\n\t")




def sample_and_pad_images(images, num_frames=8, width=512, height=512):
    frames = copy.deepcopy(images)

    if len(frames) < num_frames:
        while len(frames) < num_frames:
            frames.insert(0, Image.new("RGB", (width, height), color=(0, 0, 0)))

    latest_frame = frames[-1]
    sampled_indices = np.linspace(0, len(frames) - 1, num=num_frames - 1, endpoint=False, dtype=int)
    return [frames[i] for i in sampled_indices] + [latest_frame]


@baseline_registry.register_trainer(name="awarevln")
class AwareVLNTrainer(BaseVLNCETrainer):
    def __init__(self, config=None, num_chunks=1, chunk_idx=0):
        self.num_chunks = num_chunks
        self.chunk_idx = chunk_idx
        super().__init__(config)

    def _make_dirs(self) -> None:
        if self.config.EVAL.SAVE_RESULTS:
            self._make_results_dir()

    def train(self) -> None:
        raise NotImplementedError

    def _eval_checkpoint(
        self,
        checkpoint_path: str,
        writer: TensorboardWriter,
    ) -> None:
        logger.info(f"checkpoint_path: {checkpoint_path}")

        from case1_runtime.observations import resolve_graph_hook_switch
        graph_profile_path, graph_switch = resolve_graph_hook_switch(os.environ)
        if graph_profile_path:
            from pathlib import Path
            from graphAdapter.interfaces.pose.policy import require_simulator_profile
            profile = json.loads(Path(graph_profile_path).read_text())
            require_simulator_profile(profile)

        model_name = os.path.basename(os.path.normpath(checkpoint_path))
        tokenizer, model, image_processor, _ = load_pretrained_model(checkpoint_path, model_name, device_map={"": 0})

        reason_token_str = getattr(self.config.MODEL, "REASON_TOKEN", "<BEGIN_OF_REASONING>")
        act_token_str = getattr(self.config.MODEL, "ACT_TOKEN", "<BEGIN_OF_ACTION>")

        reason_id = tokenizer.convert_tokens_to_ids(reason_token_str)
        act_id = tokenizer.convert_tokens_to_ids(act_token_str)

        assert reason_id != -1 and act_id != -1, (
            "Tokenizer missing reasoning/action special tokens. "
            "Load the tokenizer saved with the checkpoint."
        )

        model.config.reason_token_id = reason_id
        model.config.act_token_id = act_id
        if any(parameter.is_meta for parameter in model.parameters()):
            raise RuntimeError("Model loading left meta parameters; full-GPU execution is required")
        model = model.cuda()
        TraceRecorder.model_loaded(checkpoint_path, tokenizer, model)
        hamlet = None
        if os.environ.get("CASE2_HAMLET_CONFIG"):
            from pathlib import Path
            from hamlet_v2.policy import load_policy
            from hamlet_v2.runtime import HAMLETRuntime
            hamlet = HAMLETRuntime(model, load_policy(os.environ["AWAREVLN_ROOT"]),
                                   Path(os.environ["CASE1_TRACE_ROOT"]) / "hamlet-dataflow.jsonl")


        ACTION_ID_STOP = 0
        ACTION_ID_FORWARD = 1
        ACTION_ID_LEFT = 2
        ACTION_ID_RIGHT = 3

        config = self.config.clone()
        split = config.EVAL.SPLIT
        config.defrost()
        config.TASK_CONFIG.DATASET.SPLIT = split
        config.TASK_CONFIG.DATASET.ROLES = ["guide"]
        config.TASK_CONFIG.DATASET.LANGUAGES = config.EVAL.LANGUAGES
        config.TASK_CONFIG.TASK.NDTW.SPLIT = split
        config.TASK_CONFIG.ENVIRONMENT.ITERATOR_OPTIONS.SHUFFLE = False
        config.TASK_CONFIG.ENVIRONMENT.ITERATOR_OPTIONS.MAX_SCENE_REPEAT_STEPS = -1
        config.TASK_CONFIG.DATASET.NUM_CHUNKS = self.num_chunks
        config.TASK_CONFIG.DATASET.CHUNK_IDX = self.chunk_idx
        config.RESULTS_DIR = os.path.join(
            config.RESULTS_DIR, model_name, config.TASK_CONFIG.DATASET.TYPE, config.TASK_CONFIG.DATASET.SPLIT
        )
        os.makedirs(config.RESULTS_DIR, exist_ok=True)
        config.VIDEO_DIR = os.path.join(config.RESULTS_DIR, "videos")
        config.use_pbar = not is_slurm_batch_job()
        if len(config.VIDEO_OPTION) > 0:
            config.TASK_CONFIG.TASK.MEASUREMENTS.append("TOP_DOWN_MAP_VLNCE")
        config.freeze()

        TraceRecorder.effective_configuration(config)

        reason_stuck_id_path = os.path.join(config.RESULTS_DIR, "reason_stuck_id.txt")

        if config.EVAL.SAVE_RESULTS:
            fname = os.path.join(
                config.RESULTS_DIR,
                f"{split}_{self.num_chunks}-{self.chunk_idx}.json",
            )
            if os.path.exists(fname):
                logger.info("skipping -- evaluation exists.")
                return

        envs = construct_envs_auto_reset_false(config, get_env_class(config.ENV_NAME))
        random.seed(config.TASK_CONFIG.SEED)
        np.random.seed(config.TASK_CONFIG.SEED)
        torch.manual_seed(config.TASK_CONFIG.SEED)
        observations = envs.reset()
        graph_hook = None
        if graph_profile_path:
            from graphAdapter.observation_pose.aware_hook import AwarePoseHook
            from SimulatorAdapter.host_bridge import make_vector_factory
            adapter_factory = make_vector_factory(envs, profile, env_index=0)
            graph_hook = AwarePoseHook(Path(os.environ["CASE1_TRACE_ROOT"]) / "observation_pose", profile, adapter_factory=adapter_factory)
            from graphAdapter.observation_pose.host_wiring import reset_from_environment
            reset_from_environment(graph_hook,envs,0,observations[0],episode_scope(envs.current_episodes()[0]))
        recorder = TraceRecorder.from_environment()
        def hook_receipt(completed):
            import sys
            from pathlib import Path
            value=dict(completed=completed,requested_mode=os.environ.get("CASE2_HOOK_MODE","off"),switch_resolution=graph_switch,preflight_switch_resolution=json.loads(os.environ.get("CASE2_SWITCH_PREFLIGHT_AUDIT","{}")),
                profile_requested=bool(os.environ.get("CASE2_POSE_PROFILE")),hook_enabled=graph_hook is not None,
                hook_class=(type(graph_hook).__module__+"."+type(graph_hook).__name__) if graph_hook else None,
                reset_attempts=getattr(graph_hook,"reset_attempts",0),
                native_initialization_attempts=getattr(graph_hook,"native_initialization_attempts",0),
                provider_initialization_attempts=getattr(graph_hook,"provider_initialization_attempts",0),
                pose_provider=getattr(graph_hook,"pose_provider",None),
                packet_count=getattr(graph_hook,"packet_count",0),
                broker_supplied=bool(os.environ.get("POSEADAPTER_BROKER")),
                memory_broker_supplied=bool(os.environ.get("GRAPH_MEMORY_BROKER")),
                memory_worker_started=getattr(graph_hook,"memory_started",False),
                memory_packet_count=getattr(graph_hook,"memory_packet_count",0),
                memory_session=getattr(graph_hook,"memory_session",None),
                loaded_graph_modules=sorted(name for name in sys.modules if name=="graphAdapter" or name.startswith("graphAdapter.") or name=="poseAdapter" or name.startswith("poseAdapter.") or name=="SimulatorAdapter" or name.startswith("SimulatorAdapter.") or name=="pose_interfaces" or name.startswith("pose_interfaces.")))
            (Path(os.environ["CASE1_TRACE_ROOT"])/"hook-load.json").write_text(json.dumps(value,indent=2))
        hook_receipt(False)
        def record_step(actions, stop_source="model"):
            ep = envs.current_episodes()[0]
            before = envs.call_at(0, "case1_evaluator_state")
            recorder.ensure_episode(ep, before)
            if graph_hook is not None and getattr(graph_hook,"release4",False):
                try:
                    from graphAdapter.observation_pose.host_wiring import sample_before_environment_step
                    sample_before_environment_step(graph_hook,envs,0,actions[0])
                except Exception as error:
                    recorder.abort_attempt(error,None,list(queue_actions))
                    raise
            outcome = envs.step(actions)
            capture_error = None
            try:
                if graph_hook is not None:
                    from graphAdapter.observation_pose.host_wiring import capture_from_environment
                    capture_from_environment(graph_hook,envs,0,outcome[0][0],action_id=actions[0],terminal=outcome[0][2])
            except Exception as error:
                capture_error = error
            finally:
                after = envs.call_at(0, "case1_evaluator_state")
                recorder.step(ep, actions[0], before, after, outcome[0][2], outcome[0][3], stop_source, capture_error=capture_error)
            if capture_error is not None:
                recorder.abort_attempt(capture_error,actions[0],list(queue_actions))
                raise capture_error
            return outcome
        policy_inputs = extract_instruction_tokens(
            policy_observations(observations), self.config.TASK_CONFIG.TASK.INSTRUCTION_SENSOR_UUID
        )
        batch = batch_obs(policy_inputs, self.device)
        batch = apply_obs_transforms_batch(batch, self.obs_transforms)

        stats_episodes = {}
        past_rgbs = [[] for _ in range(envs.num_envs)]
        rgb_frames = [[] for _ in range(envs.num_envs)]

        if len(config.VIDEO_OPTION) > 0:
            os.makedirs(config.VIDEO_DIR, exist_ok=True)

        num_eps = sum(envs.number_of_episodes)
        if config.EVAL.EPISODE_COUNT > -1:
            num_eps = min(config.EVAL.EPISODE_COUNT, num_eps)

        pbar = tqdm.tqdm(total=num_eps) if config.use_pbar else None
        log_str = (
            f"[Ckpt: {checkpoint_path}]"
            " [Episodes evaluated: {evaluated}/{total}]"
            " [Time elapsed (s): {time}]"
        )
        start_time = time.time()

        assert envs.num_envs == 1
        retrieval_active = False
        if graph_hook is not None:
            from graphAdapter.map_memory.retrieval import retrieval_settings
            retrieval_active = retrieval_settings(graph_hook.profile.get('map_memory', {})) is not None
        if retrieval_active:
            from graphAdapter.map_memory.retrieval import HostInjection, sample_native_rgb
        from contextlib import nullcontext
        reasoning_event = None
        queue_actions = []
        last_reasoning = ""
        last_reason_step = 0
        frame_id = 0
        reason_stuck_num = 0
        reasoning_context = ""
        raw_output_content = ""

        while envs.num_envs > 0 and len(stats_episodes) < num_eps:
            current_episodes = envs.current_episodes()

            if reason_stuck_num > 3:
                logger.warning("Reason stuck, forcing STOP.")
                if graph_hook is not None:
                    graph_hook.begin_macro(ACTION_ID_STOP,1)
                outputs = record_step([ACTION_ID_STOP], stop_source="reason_stuck")
                frame_id = 0
                reason_stuck_num = 0
                with open(reason_stuck_id_path, "a", encoding="utf-8") as f:
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    f.write(f"[{timestamp}] {str(current_episodes)}\n\n")

            elif len(queue_actions) > 0:
                outputs = record_step([queue_actions[0]])
                queue_actions.pop(0)

            else:
                with torch.no_grad():
                    curr_rgb = Image.fromarray(np.uint8(batch[0]["rgb"].cpu().numpy())).convert("RGB")
                    host_history = past_rgbs[0] + [curr_rgb]
                    num_video_frames = model.config.num_video_frames
                    instruction = current_episodes[0].instruction.instruction_text
                    memory_decision = None
                    if retrieval_active:
                        memory_decision = HostInjection.begin(graph_hook, instruction=instruction,
                            reasoning=last_reasoning, reasoning_event=reasoning_event, host_images=host_history,
                            budget=num_video_frames, sampler=sample_native_rgb)
                    if memory_decision is not None:
                        past_and_current_rgbs = memory_decision.images
                    else:
                        past_and_current_rgbs = sample_and_pad_images(host_history, num_frames=num_video_frames)
                    interleaved_images = "<image>\n" * (len(past_and_current_rgbs) - 1)

                    reasoning_context = last_reasoning
                    if reasoning_context:
                        related_step = frame_id - last_reason_step
                        question = (
                            f"Imagine you are a robot programmed for navigation tasks. You have been given a video "
                            f"of historical observations {interleaved_images}, and current observation <image>\n. "
                            f'Your assigned task is: "{instruction}". '
                            f'The reasoning from {related_step} steps ago was: "{reasoning_context}". '
                            f"Analyze this series of images to decide whether to predict the next action or to perform reasoning. "
                            f"If action prediction, decide your next action, which could be turning left or right by a specific degree, "
                            f"moving forward a certain distance, or stop if the task is completed. "
                            f"If reasoning, describe your current observations, assess task progress, and provide a high-level plan for the next steps."
                        )
                    else:
                        question = (
                            f"Imagine you are a robot programmed for navigation tasks. You have been given a video "
                            f"of historical observations {interleaved_images}, and current observation <image>\n. "
                            f'Your assigned task is: "{instruction}". '
                            f"Analyze this series of images to decide whether to predict the next action or to perform reasoning. "
                            f"If action prediction, decide your next action, which could be turning left or right by a specific degree, "
                            f"moving forward a certain distance, or stop if the task is completed. "
                            f"If reasoning, describe your current observations, assess task progress, and provide a high-level plan for the next steps."
                        )

                    original_question = question
                    def build_conversation(text):
                        conversation = conv_templates["llama_3"].copy()
                        conversation.append_message(conversation.roles[0], text)
                        conversation.append_message(conversation.roles[1], None)
                        return conversation
                    def tokenize_prompt(text):
                        return tokenizer_image_token(text, tokenizer, IMAGE_TOKEN_INDEX, return_tensors="pt")
                    if memory_decision is not None:
                        question = memory_decision.compile(original_question,
                            lambda q: build_conversation(q).get_prompt(), tokenizer, tokenize_prompt, model)
                        past_and_current_rgbs = memory_decision.images
                    conv = build_conversation(question)
                    prompt = conv.get_prompt()
                    if memory_decision is not None:
                        images_tensor = memory_decision.preprocess(image_processor, model.config, process_images,
                            cast_to_model=lambda value: value.to(model.device, dtype=torch.float16))
                    else:
                        tensor = process_images(past_and_current_rgbs, image_processor, model.config)
                        images_tensor = tensor.to(model.device, dtype=torch.float16)
                    input_ids = tokenize_prompt(prompt).unsqueeze(0).cuda()
                    stop_str = conv.sep if conv.sep_style != SeparatorStyle.TWO else conv.sep2
                    stopping_criteria = KeywordsStoppingCriteria([stop_str], tokenizer, input_ids)

                    recorder.ensure_episode(current_episodes[0], envs.call_at(0, "case1_evaluator_state"))
                    recorded_call_id = recorder.begin_model_call(current_episodes[0], frame_id, prompt, past_and_current_rgbs, input_ids, images_tensor, stop_str, conv.sep2)
                    projection = nullcontext()
                    if memory_decision is not None:
                        projection = memory_decision.generation(model=model,call_id=recorded_call_id,
                            images_tensor=images_tensor,prompt=prompt,input_ids=input_ids,
                            tokenize_prompt=tokenize_prompt,image_token_id=IMAGE_TOKEN_INDEX,
                            generation_config=dict(do_sample=False,temperature=0.0,max_new_tokens=256,use_cache=True,
                                pad_token_id=tokenizer.eos_token_id,stop_str=stop_str,sep2=conv.sep2))
                    if graph_hook is not None and memory_decision is None:
                        graph_hook.decision()
                    _graph_model_started_ns = None
                    if graph_hook is not None and graph_hook.memory_stream is not None:
                        import time as _graph_clock
                        _graph_model_started_ns = _graph_clock.monotonic_ns()
                    with torch.inference_mode(), projection:
                        if hamlet is None:
                            output_ids = model.generate(
                                input_ids,
                                images=images_tensor.half().cuda(),
                                do_sample=False,
                                temperature=0.0,
                                max_new_tokens=256,
                                use_cache=True,
                                stopping_criteria=[stopping_criteria],
                                pad_token_id=tokenizer.eos_token_id,
                            )
                        else:
                            output_ids = hamlet.generate(
                                episode=current_episodes[0].episode_id,
                                call_id=recorded_call_id, frame=frame_id,
                                input_ids=input_ids, images=images_tensor.half().cuda(),
                                do_sample=False, temperature=0.0, max_new_tokens=256,
                                use_cache=True, stopping_criteria=[stopping_criteria],
                                pad_token_id=tokenizer.eos_token_id,
                            )

                    outputs = tokenizer.batch_decode(output_ids, skip_special_tokens=False)[0].strip()
                    if _graph_model_started_ns is not None:
                        graph_hook.record_model_interval(recorded_call_id, _graph_model_started_ns, _graph_clock.monotonic_ns())
                    raw_decoded_for_trace = outputs
                    if outputs.endswith(stop_str):
                        outputs = outputs[: -len(stop_str)].strip()
                    if outputs.endswith(conv.sep2):
                        outputs = outputs[: -len(conv.sep2)].strip()
                    if outputs.startswith("<|begin_of_text|>"):
                        outputs = outputs[len("<|begin_of_text|>") :].strip()

                    recorder.ensure_episode(current_episodes[0], envs.call_at(0, "case1_evaluator_state"))
                    recorder.finish_model_call(recorded_call_id, output_ids, raw_decoded_for_trace, outputs)
                    is_reasoning_mode = False
                    raw_output_content = outputs
                    if outputs.startswith(reason_token_str):
                        is_reasoning_mode = True
                        raw_output_content = outputs[len(reason_token_str) :].strip()
                    elif outputs.startswith(act_token_str):
                        raw_output_content = outputs[len(act_token_str) :].strip()

                    if is_reasoning_mode:
                        last_reasoning = extract_reasoning(raw_output_content)
                        if memory_decision is not None:
                            reasoning_event = memory_decision.record_reasoning(recorded_call_id,last_reasoning)
                        reason_stuck_num += 1
                        last_reason_step = frame_id
                        continue

                    patterns = {
                        ACTION_ID_STOP: re.compile(r"\bstop\b", re.IGNORECASE),
                        ACTION_ID_FORWARD: re.compile(r"move forward", re.IGNORECASE),
                        ACTION_ID_LEFT: re.compile(r"turn left", re.IGNORECASE),
                        ACTION_ID_RIGHT: re.compile(r"turn right", re.IGNORECASE),
                    }

                    def map_string_to_action(s):
                        for action, pattern in patterns.items():
                            if pattern.search(s):
                                return action
                        return ACTION_ID_FORWARD

                    try:
                        actions = [map_string_to_action(raw_output_content)]
                    except Exception:
                        actions = [ACTION_ID_FORWARD]

                    if hamlet is not None:
                        hamlet.action_decision(actions[0], recorded_call_id)

                    if actions[0] == ACTION_ID_FORWARD:
                        try:
                            match = re.search(r"move forward (\d+) cm", raw_output_content)
                            distance = int(match.group(1))
                        except Exception:
                            distance = 25
                        if (distance % 25) != 0:
                            distance = min([25, 50, 75], key=lambda x: abs(x - distance))
                        if graph_hook is not None:
                            graph_hook.begin_macro(ACTION_ID_FORWARD, max(1, int(distance // 25)))
                        outputs = record_step([ACTION_ID_FORWARD])
                        for _ in range(int(distance // 25) - 1):
                            queue_actions.append(ACTION_ID_FORWARD)

                    elif actions[0] == ACTION_ID_LEFT:
                        try:
                            match = re.search(r"turn left (\d+) degree", raw_output_content)
                            degree = int(match.group(1))
                        except Exception:
                            degree = 15
                        if (degree % 15) != 0:
                            degree = min([15, 30, 45], key=lambda x: abs(x - degree))
                        if graph_hook is not None:
                            graph_hook.begin_macro(ACTION_ID_LEFT, max(1, int(degree // 15)))
                        outputs = record_step([ACTION_ID_LEFT])
                        for _ in range(int(degree // 15) - 1):
                            queue_actions.append(ACTION_ID_LEFT)

                    elif actions[0] == ACTION_ID_RIGHT:
                        try:
                            match = re.search(r"turn right (\d+) degree", raw_output_content)
                            degree = int(match.group(1))
                        except Exception:
                            degree = 15
                        if (degree % 15) != 0:
                            degree = min([15, 30, 45], key=lambda x: abs(x - degree))
                        if graph_hook is not None:
                            graph_hook.begin_macro(ACTION_ID_RIGHT, max(1, int(degree // 15)))
                        outputs = record_step([ACTION_ID_RIGHT])
                        for _ in range(int(degree // 15) - 1):
                            queue_actions.append(ACTION_ID_RIGHT)

                    else:
                        if graph_hook is not None:
                            graph_hook.begin_macro(actions[0], 1)
                        outputs = record_step(actions)
                        frame_id = 0
                        reason_stuck_num = 0

            observations, _, dones, infos = [list(x) for x in zip(*outputs)]
            reason_stuck_num = 0
            frame_id += 1

            for i in range(envs.num_envs):
                if dones[i]:
                    frame_id = 0
                    last_reasoning = ""

                past_rgbs[i].append(Image.fromarray(batch[0]["rgb"].cpu().numpy()).convert("RGB"))

                if len(config.VIDEO_OPTION) > 0:
                    del observations[i]["depth"]
                    frame = observations_to_image(observations[i], infos[i])
                    frame = append_text_to_image(
                        frame,
                        f"Instruction: {current_episodes[i].instruction.instruction_text}\n"
                        f"Reasoning Input: {reasoning_context}\n"
                        f"Model Output: {raw_output_content}",
                    )
                    rgb_frames[i].append(frame)

                if not dones[i]:
                    continue

                ep_id = current_episodes[i].episode_id
                stats_episodes[ep_id] = infos[i]
                if hamlet is not None:
                    hamlet.end_episode(ep_id)
                if graph_hook is not None:
                    graph_hook.end_episode(queue_actions)
                queue_actions.clear()
                last_reasoning = ""
                last_reason_step = 0
                reasoning_event = None
                frame_id = 0
                reason_stuck_num = 0
                reasoning_context = ""
                raw_output_content = ""
                random.seed(config.TASK_CONFIG.SEED)
                np.random.seed(config.TASK_CONFIG.SEED)
                torch.manual_seed(config.TASK_CONFIG.SEED)
                observations[i] = envs.reset_at(i)[0]
                if graph_hook is not None and len(stats_episodes) < num_eps:
                    from graphAdapter.observation_pose.host_wiring import reset_from_environment
                    reset_from_environment(graph_hook,envs,0,observations[i],episode_scope(envs.current_episodes()[0]))
                past_rgbs[i] = []

                if config.use_pbar:
                    pbar.update()
                else:
                    logger.info(
                        log_str.format(
                            evaluated=len(stats_episodes),
                            total=num_eps,
                            time=round(time.time() - start_time),
                        )
                    )

                if len(config.VIDEO_OPTION) > 0:
                    del stats_episodes[ep_id]["top_down_map_vlnce"]
                    rgb_frames[i] = []

            policy_inputs = extract_instruction_tokens(
                policy_observations(observations),
                self.config.TASK_CONFIG.TASK.INSTRUCTION_SENSOR_UUID,
            )
            batch = batch_obs(policy_inputs, self.device)
            batch = apply_obs_transforms_batch(batch, self.obs_transforms)

            envs_to_pause = []
            next_episodes = envs.current_episodes()
            for i in range(envs.num_envs):
                if next_episodes[i].episode_id in stats_episodes:
                    envs_to_pause.append(i)

            envs, batch, rgb_frames = self._pause_envs(
                envs_to_pause,
                envs,
                batch,
                rgb_frames,
            )

        if hamlet is not None:
            hamlet.close()
        if graph_hook is not None:
            graph_hook.close()
        hook_receipt(True)
        recorder.close()
        envs.close()
        if config.use_pbar:
            pbar.close()

        if config.EVAL.SAVE_RESULTS:
            with open(fname, "w") as f:
                json.dump(stats_episodes, f, indent=4)

    @staticmethod
    def _pause_envs(
        envs_to_pause,
        envs,
        batch,
        rgb_frames=None,
    ):
        if len(envs_to_pause) > 0:
            state_index = list(range(envs.num_envs))
            for idx in reversed(envs_to_pause):
                state_index.pop(idx)
                envs.pause_at(idx)

            for k, v in batch.items():
                batch[k] = v[state_index]

            if rgb_frames is not None:
                rgb_frames = [rgb_frames[i] for i in state_index]

        return envs, batch, rgb_frames

    def eval(self) -> None:
        self.device = (
            torch.device("cuda", self.config.TORCH_GPU_ID)
            if torch.cuda.is_available()
            else torch.device("cpu")
        )
        if "tensorboard" in self.config.VIDEO_OPTION:
            assert len(self.config.TENSORBOARD_DIR) > 0, "Must specify a tensorboard directory for video display"
            os.makedirs(self.config.TENSORBOARD_DIR, exist_ok=True)
        if "disk" in self.config.VIDEO_OPTION:
            assert len(self.config.VIDEO_DIR) > 0, "Must specify a directory for storing videos on disk"

        with TensorboardWriter(self.config.TENSORBOARD_DIR, flush_secs=self.flush_secs) as writer:
            if os.path.isdir(self.config.EVAL_CKPT_PATH_DIR):
                self._eval_checkpoint(
                    self.config.EVAL_CKPT_PATH_DIR,
                    writer,
                )
