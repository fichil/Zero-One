#!/usr/bin/env python3
"""Export shot prompts from a Zero-One episode JSON file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_episode(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def default_output_path(episode: dict) -> Path:
    episode_id = episode["episode_id"].lower()
    return Path("outputs") / episode_id / "prompts_export.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", nargs="?", default="episodes/ep001_moon_pink.json")
    parser.add_argument("-o", "--output")
    args = parser.parse_args()

    episode = load_episode(Path(args.episode))
    output_path = Path(args.output) if args.output else default_output_path(episode)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "episode_id": episode["episode_id"],
        "title": episode["title"],
        "platform": episode["platform"],
        "aspect_ratio": episode["aspect_ratio"],
        "duration_seconds": episode["duration_seconds"],
        "experiment_id": episode["experiment_id"],
        "character_bible": episode["prompts"]["character_bible"],
        "visual_style": episode["prompts"]["visual_style"],
        "negative_prompts": episode["prompts"]["negative_prompts"],
        "shots": episode["prompts"]["shots"],
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
