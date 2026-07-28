#!/usr/bin/env python3
"""Convert a small extracted AwareVLN subset into Qwen3-VL SFT JSON."""

from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path
from typing import Any

import numpy as np


FRAME_RE = re.compile(r"frame_(\d+)\.(?:jpg|jpeg|png)$", re.IGNORECASE)


def get_segment(cot: dict[str, Any], episode: str, step: int) -> dict[str, Any]:
    for segment in cot.get(episode, {}).get("segments", []):
        end = 10_000 if segment["end_step"] == -1 else segment["end_step"]
        if segment["start_step"] <= step < end:
            return segment
    return {
        "content": "No active planning.",
        "updated_content": None,
        "type": "only_act",
        "reference_start_step": 0,
        "reference_end_step": step + 1,
    }


def reasoning_probability(start: int, end: int, now: int) -> float:
    if end <= start:
        return 0.75
    peak = start + (end - start) / 4
    if now <= peak:
        ratio = (now - start) / (peak - start)
        return 0.5 + (0.75 - 0.5) * ratio
    ratio = (now - peak) / (end - peak)
    return 0.75 - (0.75 - 0.3) * ratio


def pick_index(rng: random.Random, start: int, end_exclusive: int) -> int:
    if end_exclusive <= start:
        return max(0, start)
    return rng.randrange(max(0, start), end_exclusive)


def choose_target(
    row: dict[str, Any], segment: dict[str, Any], last_frame: int, rng: random.Random
) -> tuple[str, str, int]:
    old = segment.get("content") or ""
    new = segment.get("updated_content") or ""
    kind = segment.get("type")
    ref_start = int(segment.get("reference_start_step", 0))
    ref_end = int(segment.get("reference_end_step", last_frame + 1))
    if ref_end < 0:
        ref_end = 1000
    old_ref_end = min(ref_end, last_frame + 1)

    if new and kind in {"newroom", "correction_part2"}:
        start = int(segment.get("start_step", last_frame))
        end = int(segment.get("end_step", last_frame + 10))
        if end < 0:
            end = 1000
        if rng.random() < reasoning_probability(start, end, last_frame):
            return (
                "reason",
                f"[REASON] New reasoning is: '{new}'",
                pick_index(rng, ref_start, old_ref_end),
            )
        if rng.random() < 0.3:
            return "act", f"[ACT] {row['a'].strip()}", pick_index(rng, ref_start, old_ref_end)
        return "act", f"[ACT] {row['a'].strip()}", pick_index(rng, start, last_frame + 1)

    if new and kind in {"correction_part1", "correction_tail"}:
        start = int(segment.get("start_step", last_frame))
        reason_index = int(segment.get("index", last_frame))
        if last_frame < reason_index or (last_frame == reason_index and rng.random() < 0.3):
            return (
                "reason",
                f"[REASON] New reasoning is: '{new}'",
                pick_index(rng, ref_start, old_ref_end),
            )
        if rng.random() < 0.5:
            return "act", f"[ACT] {row['a'].strip()}", pick_index(rng, ref_start, old_ref_end)
        return "act", f"[ACT] {row['a'].strip()}", pick_index(rng, start, last_frame + 1)

    if rng.random() < 0.9:
        return "act", f"[ACT] {row['a'].strip()}", pick_index(rng, ref_start, old_ref_end)
    return "act", f"[ACT] {row['a'].strip()}", last_frame


def sample_frames(episode: str, last_frame: int, count: int = 8) -> list[str]:
    history = [f"{episode}/frame_{index}.jpg" for index in range(last_frame + 1)]
    sampled = np.linspace(0, len(history) - 1, num=count - 1, endpoint=False, dtype=int)
    return [history[index] for index in sampled] + [history[-1]]


def build_prompt(instruction: str, reasoning: str, related_step: int, frame_count: int) -> str:
    images = "<image>\n" * frame_count
    prior = ""
    if reasoning:
        prior = f'The reasoning from {related_step} steps ago was: "{reasoning}". '
    return (
        f"{images}Imagine you are a robot programmed for navigation tasks. "
        f'You have been given {frame_count - 1} historical observations and one current observation. '
        f'Your assigned task is: "{instruction.strip()}". '
        f"{prior}Analyze this series of images to decide whether to predict the next action or to perform reasoning. "
        "If action prediction, decide your next action, which could be turning left or right by a specific degree, "
        "moving forward a certain distance, or stop if the task is completed. "
        "If reasoning, describe your current observations, assess task progress, and provide a high-level plan for the next steps."
    )


def build_action_prompt(instruction: str, frame_count: int) -> str:
    """Build the NaVILA-style Stage-1 prompt with action-only supervision."""
    images = "<image>\n" * frame_count
    return (
        f"{images}Imagine you are a robot programmed for navigation tasks. "
        f'You have been given {frame_count - 1} historical observations and one current observation. '
        f'Your assigned task is: "{instruction.strip()}". '
        "Analyze this series of images and predict the next action. The action can be turning left or right "
        "by a specific degree, moving forward a certain distance, or stopping if the task is completed. "
        "Answer with the next action only."
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=10)
    parser.add_argument("--max-samples", type=int, default=32)
    parser.add_argument("--min-last-frame", type=int, default=7)
    parser.add_argument(
        "--stage",
        choices=("aware", "action"),
        default="aware",
        help="aware: mixed [ACT]/[REASON] targets; action: NaVILA-style action-only targets",
    )
    parser.add_argument("--output-subdir", default="qwen3_sft")
    args = parser.parse_args()

    subset = args.data_root / "reason/r2rfollow"
    anno_dir = subset / "_anno_cot"
    videos = subset / "videos"
    manifest = json.loads((subset / "stream_extract_manifest.json").read_text())
    episodes = set(manifest["selected_episodes"])
    annotations = json.loads((anno_dir / "annotations_shuffle_uni.json").read_text())
    cot = json.loads((anno_dir / "cot_new.json").read_text())
    rng = random.Random(args.seed)

    converted: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    filtered_annotations: list[dict[str, Any]] = []

    candidates = []
    for row in annotations:
        frame_path = row.get("frames", [""])[-1]
        match = FRAME_RE.search(frame_path)
        episode = Path(frame_path).parent.name
        if episode not in episodes or match is None:
            continue
        last_frame = int(match.group(1))
        if last_frame < args.min_last_frame:
            continue
        candidates.append((last_frame, row, episode))

    candidates.sort(key=lambda item: item[0])
    for last_frame, row, episode in candidates:
        frames = sample_frames(episode, last_frame)
        missing = [frame for frame in frames if not (videos / frame).is_file()]
        if missing:
            continue

        segment = get_segment(cot, episode, last_frame)
        if args.stage == "action":
            target_kind = "act"
            target = row["a"].strip()
            reference = last_frame
            prompt = build_action_prompt(row["q"], len(frames))
        else:
            target_kind, target, reference = choose_target(row, segment, last_frame, rng)
            reasoning = segment.get("content") or ""
            if (
                target_kind == "act"
                and segment.get("updated_content")
                and reference >= segment.get("start_step", 0)
            ):
                reasoning = segment["updated_content"]
            prompt = build_prompt(row["q"], reasoning, last_frame - reference, len(frames))
        converted.append(
            {
                "image": frames,
                "conversations": [
                    {"from": "human", "value": prompt},
                    {"from": "gpt", "value": target},
                ],
            }
        )
        records.append(
            {
                "video_id": row["video_id"],
                "episode": episode,
                "last_frame": last_frame,
                "sampled_frames": frames,
                "target_kind": target_kind,
                "target": target,
            }
        )
        filtered_annotations.append(row)
        if len(converted) >= args.max_samples:
            break

    if not converted:
        raise RuntimeError("No valid samples were produced")

    output = subset / args.output_subdir
    output.mkdir(parents=True, exist_ok=True)
    (output / "train.json").write_text(json.dumps(converted, indent=2), encoding="utf-8")
    preferred = next((i for i, record in enumerate(records) if record["target_kind"] == "reason"), 0)
    (output / "one_sample.json").write_text(
        json.dumps([converted[preferred]], indent=2), encoding="utf-8"
    )
    (output / "manifest.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    (output / "annotations_filtered.json").write_text(
        json.dumps(filtered_annotations, indent=2), encoding="utf-8"
    )
    (output / "cot_filtered.json").write_text(
        json.dumps({episode: cot[episode] for episode in episodes if episode in cot}, indent=2),
        encoding="utf-8",
    )

    counts = {kind: sum(r["target_kind"] == kind for r in records) for kind in ("act", "reason")}
    print(f"Wrote {len(converted)} samples to {output / 'train.json'}")
    print(f"Targets: {counts}; one-sample index: {preferred}")
    print(json.dumps(records[preferred], indent=2))


if __name__ == "__main__":
    main()
