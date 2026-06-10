#!/usr/bin/env python3
"""Validate a production-ready Zero-One episode JSON file."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


REQUIRED_SHOT_FIELDS = [
    "shot_id",
    "duration_sec",
    "visual",
    "dialogue",
    "caption",
    "image_prompt",
    "video_prompt",
    "voice",
]

OPTIONAL_PRODUCTION_FIELDS = [
    "type",
    "character_action",
]


def load_episode(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def require_non_empty_string(value: object, label: str) -> None:
    require(isinstance(value, str) and value.strip(), f"{label} must be a non-empty string")


def validate_shots(shots: object) -> tuple[int, int]:
    require(isinstance(shots, list) and shots, "shots must be a non-empty array")

    total_duration = 0
    seen_ids: set[str] = set()
    for index, shot in enumerate(shots, start=1):
        require(isinstance(shot, dict), f"shots[{index}] must be an object")

        for field in REQUIRED_SHOT_FIELDS:
            require(field in shot, f"shots[{index}] missing field: {field}")
        for field in OPTIONAL_PRODUCTION_FIELDS:
            require(field in shot, f"shots[{index}] missing production field: {field}")

        shot_id = shot["shot_id"]
        require(isinstance(shot_id, str), f"shots[{index}].shot_id must be a string")
        require(re.fullmatch(r"s\d{2}", shot_id) is not None, f"bad shot_id: {shot_id}")
        require(shot_id not in seen_ids, f"duplicate shot_id: {shot_id}")
        seen_ids.add(shot_id)

        duration = shot["duration_sec"]
        require(isinstance(duration, int) and duration > 0, f"{shot_id}.duration_sec must be a positive integer")
        total_duration += duration

        for field in ["visual", "dialogue", "caption", "image_prompt", "video_prompt", "voice"]:
            require_non_empty_string(shot[field], f"{shot_id}.{field}")

    require(45 <= total_duration <= 90, f"total duration {total_duration}s is outside 45-90 seconds")
    return len(shots), total_duration


def validate_episode(episode: dict) -> tuple[int, int]:
    require(isinstance(episode, dict), "episode JSON must be an object")
    require(episode.get("aspect_ratio") == "9:16", "aspect_ratio must be 9:16 for vertical video")
    require("shots" in episode, "missing top-level key: shots")
    return validate_shots(episode["shots"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", nargs="?", default="episodes/ep001_moon_pink.json")
    args = parser.parse_args()

    path = Path(args.episode)
    try:
        episode = load_episode(path)
        shot_count, total_duration = validate_episode(episode)
    except json.JSONDecodeError as exc:
        print(f"Validation failed: invalid JSON: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return 1

    print("JSON OK")
    print("vertical_video=True")
    print(f"shots={shot_count}")
    print(f"total_duration_sec={total_duration}")
    print("duration_range=45-90")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
