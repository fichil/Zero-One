#!/usr/bin/env python3
"""Generate an SRT subtitle file from episode voiceover segments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_episode(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def format_time(total_seconds: int) -> str:
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},000"


def build_srt(segments: list[dict]) -> str:
    blocks: list[str] = []
    cursor = 0
    for index, segment in enumerate(segments, start=1):
        start = cursor
        end = cursor + segment["duration_seconds"]
        text = segment["text"].strip()
        blocks.append(
            f"{index}\n"
            f"{format_time(start)} --> {format_time(end)}\n"
            f"{text}\n"
        )
        cursor = end
    return "\n".join(blocks)


def default_output_path(episode: dict) -> Path:
    episode_id = episode["episode_id"].lower()
    return Path("outputs") / episode_id / f"{episode_id}_subtitles.srt"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", nargs="?", default="episodes/ep001_moon_pink.json")
    parser.add_argument("-o", "--output")
    args = parser.parse_args()

    episode = load_episode(Path(args.episode))
    output_path = Path(args.output) if args.output else default_output_path(episode)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    srt = build_srt(episode["voiceover"]["segments"])
    output_path.write_text(srt, encoding="utf-8")
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
