#!/usr/bin/env python3
"""Validate a Zero-One episode production JSON file."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


K_SHOT_ID = "\u955c\u5934\u7f16\u53f7"
K_DURATION = "\u65f6\u957f\u79d2"


def load_episode(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def shot_map(items: list[dict], label: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in items:
        require(K_SHOT_ID in item, f"{label}: missing shot id")
        require(K_DURATION in item, f"{label}: missing duration for {item.get(K_SHOT_ID)}")
        shot_id = item[K_SHOT_ID]
        duration = item[K_DURATION]
        require(isinstance(shot_id, str), f"{label}: shot id must be a string")
        require(re.fullmatch(r"S\d{2}", shot_id) is not None, f"{label}: bad shot id {shot_id}")
        require(isinstance(duration, int), f"{label}: duration must be an integer for {shot_id}")
        require(duration > 0, f"{label}: duration must be positive for {shot_id}")
        require(shot_id not in result, f"{label}: duplicate shot id {shot_id}")
        result[shot_id] = duration
    return result


def segment_map(items: list[dict]) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in items:
        shot_id = item.get("shot_id")
        duration = item.get("duration_seconds")
        require(isinstance(shot_id, str), "voiceover: shot_id must be a string")
        require(re.fullmatch(r"S\d{2}", shot_id) is not None, f"voiceover: bad shot id {shot_id}")
        require(isinstance(duration, int), f"voiceover: duration must be an integer for {shot_id}")
        require(isinstance(item.get("text"), str) and item["text"].strip(), f"voiceover: empty text for {shot_id}")
        require(shot_id not in result, f"voiceover: duplicate shot id {shot_id}")
        result[shot_id] = duration
    return result


def validate_episode(episode: dict) -> None:
    required = [
        "episode_id",
        "title",
        "platform",
        "aspect_ratio",
        "duration_seconds",
        "experiment_id",
        "storyboard",
        "prompts",
        "voiceover",
        "assets_plan",
    ]
    for key in required:
        require(key in episode, f"missing top-level key: {key}")

    require(episode["episode_id"] == "EP001", "episode_id must be EP001")
    require(episode["experiment_id"] == "Universe-0001", "experiment_id must be Universe-0001")
    require(episode["duration_seconds"] == 60, "duration_seconds must be 60")
    require(episode["aspect_ratio"] == "9:16", "aspect_ratio must be 9:16")

    storyboard = episode["storyboard"]
    prompts = episode["prompts"]
    voiceover = episode["voiceover"]
    assets_plan = episode["assets_plan"]

    storyboard_shots = shot_map(storyboard.get("shots", []), "storyboard")
    prompt_shots = shot_map(prompts.get("shots", []), "prompts")
    asset_shots = shot_map(assets_plan.get("shot_asset_map", []), "assets_plan")
    voiceover_shots = segment_map(voiceover.get("segments", []))

    expected_ids = [f"S{i:02d}" for i in range(1, 11)]
    require(list(storyboard_shots.keys()) == expected_ids, "storyboard shot ids must be S01-S10")
    require(prompt_shots == storyboard_shots, "prompts shots must align with storyboard")
    require(asset_shots == storyboard_shots, "asset map shots must align with storyboard")
    require(voiceover_shots == storyboard_shots, "voiceover segments must align with storyboard")
    require(sum(storyboard_shots.values()) == episode["duration_seconds"], "shot durations must total 60 seconds")

    flat = json.dumps(episode, ensure_ascii=False)
    require("Universe-0001" in flat, "episode must contain Universe-0001")
    require("\u65b9\u7cd6" in flat, "episode must contain Fangtang")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", nargs="?", default="episodes/ep001_moon_pink.json")
    args = parser.parse_args()

    path = Path(args.episode)
    try:
        episode = load_episode(path)
        validate_episode(episode)
    except Exception as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return 1

    print(f"OK: {path}")
    print("episode_id=EP001")
    print("shots=10")
    print("duration_seconds=60")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
