#!/usr/bin/env python3
"""Stream a Hugging Face tar.gz and keep only the first N episode folders.

This deliberately uses tar streaming mode (r|gz): the 50+ GB archive is never
stored locally, and the HTTP connection is closed when the requested number of
complete, consecutively stored episode directories has been read.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import tarfile
from pathlib import Path, PurePosixPath

import requests
from huggingface_hub import hf_hub_url
from huggingface_hub.utils import build_hf_headers


FRAME_RE = re.compile(r"^frame_(\d+)\.(?:jpg|jpeg|png)$", re.IGNORECASE)


class CountingReader:
    def __init__(self, raw):
        self.raw = raw
        self.bytes_read = 0

    def read(self, size=-1):
        chunk = self.raw.read(size)
        self.bytes_read += len(chunk)
        return chunk

    def readable(self):
        return True


def frame_location(member_name: str) -> tuple[str, str] | None:
    parts = PurePosixPath(member_name.lstrip("./")).parts
    if len(parts) < 2 or not FRAME_RE.match(parts[-1]):
        return None
    episode = parts[-2]
    if episode in {"", ".", ".."} or "/" in episode or "\\" in episode:
        return None
    return episode, parts[-1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-id", default="gwx22/AwareVLN")
    parser.add_argument(
        "--archive", default="reason/r2rfollow/videos.tar.gz"
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--episodes", type=int, default=1)
    args = parser.parse_args()

    if args.episodes < 1:
        raise ValueError("--episodes must be at least 1")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    url = hf_hub_url(args.repo_id, args.archive, repo_type="dataset")
    headers = build_hf_headers()
    selected: list[str] = []
    frame_counts: dict[str, int] = {}
    completed = False

    with requests.get(
        url, headers=headers, stream=True, allow_redirects=True, timeout=(30, 300)
    ) as response:
        response.raise_for_status()
        response.raw.decode_content = True
        reader = CountingReader(response.raw)

        with tarfile.open(fileobj=reader, mode="r|gz") as archive:
            for member in archive:
                if not member.isfile():
                    continue
                location = frame_location(member.name)
                if location is None:
                    continue
                episode, filename = location

                if episode not in selected:
                    if len(selected) >= args.episodes:
                        completed = True
                        break
                    selected.append(episode)
                    frame_counts[episode] = 0
                    print(f"Selected episode {episode}", flush=True)

                if episode not in selected:
                    continue

                source = archive.extractfile(member)
                if source is None:
                    continue
                target_dir = args.output_dir / episode
                target_dir.mkdir(parents=True, exist_ok=True)
                target = target_dir / filename
                with target.open("wb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                frame_counts[episode] += 1

                if frame_counts[episode] % 100 == 0:
                    mib = reader.bytes_read / 1024**2
                    print(
                        f"{episode}: {frame_counts[episode]} frames, "
                        f"downloaded {mib:.1f} MiB",
                        flush=True,
                    )

        manifest = {
            "repo_id": args.repo_id,
            "archive": args.archive,
            "selected_episodes": selected,
            "frame_counts": frame_counts,
            "downloaded_bytes": reader.bytes_read,
            "stopped_at_next_episode": completed,
        }

    manifest_path = args.output_dir.parent / "stream_extract_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2), flush=True)
    print(f"Manifest: {manifest_path}", flush=True)


if __name__ == "__main__":
    main()
