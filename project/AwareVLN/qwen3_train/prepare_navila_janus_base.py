#!/usr/bin/env python3
"""Build a canonical Qwen3 action-SFT mixture from NaVILA and JanusVLN data."""

from __future__ import annotations

import argparse
import gzip
import json
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from prepare_qwen3_sft import build_action_prompt


JANUS_IMAGE_RE = re.compile(
    r"^step_(\d+)_(MOVE_FORWARD|TURN_LEFT|TURN_RIGHT|STOP)\.png$",
    re.IGNORECASE,
)
ACTION_TEXT = {
    "MOVE_FORWARD": "The next action is move forward 25 cm.",
    "TURN_LEFT": "The next action is turn left 15 degree.",
    "TURN_RIGHT": "The next action is turn right 15 degree.",
    "STOP": "I think I should stop because I have finished the instruction.",
}


def sample_history(paths: list[Path], current: int, count: int = 8) -> list[Path]:
    available = paths[: current + 1]
    indices = np.linspace(0, len(available) - 1, num=count - 1, endpoint=False, dtype=int)
    return [available[index] for index in indices] + [available[-1]]


def load_instructions(path: Path) -> dict[str, str]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        data = json.load(handle)
    return {
        str(episode["episode_id"]): episode["instruction"]["instruction_text"].strip()
        for episode in data["episodes"]
    }


def build_janus_candidates(
    image_root: Path, instructions: dict[str, str], min_last_frame: int
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for episode_dir in sorted(path for path in image_root.iterdir() if path.is_dir()):
        instruction = instructions.get(episode_dir.name)
        if not instruction:
            continue
        parsed: list[tuple[int, str, Path]] = []
        for image in episode_dir.glob("step_*.png"):
            match = JANUS_IMAGE_RE.match(image.name)
            if match:
                parsed.append((int(match.group(1)), match.group(2).upper(), image.resolve()))
        parsed.sort(key=lambda item: item[0])
        paths = [item[2] for item in parsed]
        for index, (step, action, _) in enumerate(parsed):
            if index < min_last_frame:
                continue
            frames = sample_history(paths, index)
            candidates.append(
                {
                    "source": "janusvln_r2r",
                    "episode": episode_dir.name,
                    "step": step,
                    "action_class": action,
                    "image": [str(path) for path in frames],
                    "conversations": [
                        {"from": "human", "value": build_action_prompt(instruction, len(frames))},
                        {"from": "gpt", "value": ACTION_TEXT[action]},
                    ],
                }
            )
    return candidates


def balanced_sample(rows: list[dict[str, Any]], limit: int, rng: random.Random) -> list[dict[str, Any]]:
    if limit <= 0 or len(rows) <= limit:
        result = list(rows)
        rng.shuffle(result)
        return result
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["action_class"]].append(row)
    for group in groups.values():
        rng.shuffle(group)

    selected: list[dict[str, Any]] = []
    # Preserve rare STOP examples first, then fill round-robin across action classes.
    if groups.get("STOP"):
        selected.extend(groups["STOP"][: min(len(groups["STOP"]), 2)])
        groups["STOP"] = groups["STOP"][min(len(groups["STOP"]), 2) :]
    order = ["MOVE_FORWARD", "TURN_LEFT", "TURN_RIGHT", "STOP"]
    while len(selected) < limit and any(groups.get(action) for action in order):
        for action in order:
            if groups.get(action) and len(selected) < limit:
                selected.append(groups[action].pop())
    rng.shuffle(selected)
    return selected


def canonicalize_navila(path: Path, image_root: Path) -> list[dict[str, Any]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    result = []
    for index, row in enumerate(rows):
        copied = dict(row)
        copied["source"] = "navila_aware_r2rfollow"
        copied["sample_id"] = f"navila-{index}"
        copied["image"] = [str((image_root / image).resolve()) for image in row["image"]]
        result.append(copied)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--navila-json", type=Path, required=True)
    parser.add_argument("--navila-image-root", type=Path, required=True)
    parser.add_argument("--janus-image-root", type=Path, required=True)
    parser.add_argument("--r2r-episodes", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--janus-max-samples", type=int, default=28)
    parser.add_argument("--min-last-frame", type=int, default=7)
    parser.add_argument("--seed", type=int, default=10)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    navila = canonicalize_navila(args.navila_json, args.navila_image_root)
    janus_all = build_janus_candidates(
        args.janus_image_root,
        load_instructions(args.r2r_episodes),
        args.min_last_frame,
    )
    janus = balanced_sample(janus_all, args.janus_max_samples, rng)
    mixture = navila + janus
    rng.shuffle(mixture)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    train_rows = [
        {key: value for key, value in row.items() if key in {"image", "conversations"}}
        for row in mixture
    ]
    (args.output_dir / "train.json").write_text(
        json.dumps(train_rows, indent=2), encoding="utf-8"
    )
    (args.output_dir / "manifest.json").write_text(
        json.dumps(mixture, indent=2), encoding="utf-8"
    )
    first_janus = next(row for row in mixture if row["source"] == "janusvln_r2r")
    (args.output_dir / "one_sample.json").write_text(
        json.dumps(
            [{key: value for key, value in first_janus.items() if key in {"image", "conversations"}}],
            indent=2,
        ),
        encoding="utf-8",
    )
    counts: dict[str, int] = defaultdict(int)
    for row in mixture:
        counts[row["source"]] += 1
    action_counts: dict[str, int] = defaultdict(int)
    for row in janus:
        action_counts[row["action_class"]] += 1
    print(f"Wrote {len(mixture)} mixed samples to {args.output_dir / 'train.json'}")
    print(f"Sources: {dict(counts)}")
    print(f"Janus actions: {dict(action_counts)}")


if __name__ == "__main__":
    main()
