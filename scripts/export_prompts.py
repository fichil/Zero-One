#!/usr/bin/env python3
"""Export image prompts, video prompts, and voice lines from an episode JSON file."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def load_episode(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def default_output_dir(episode: dict) -> Path:
    return Path("outputs") / episode["episode_id"]


def write_image_prompts(path: Path, shots: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["shot_id", "duration_sec", "visual", "image_prompt"])
        writer.writeheader()
        for shot in shots:
            writer.writerow(
                {
                    "shot_id": shot["shot_id"],
                    "duration_sec": shot["duration_sec"],
                    "visual": shot["visual"],
                    "image_prompt": shot["image_prompt"],
                }
            )


def write_video_prompts(path: Path, shots: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["shot_id", "duration_sec", "visual", "video_prompt"])
        writer.writeheader()
        for shot in shots:
            writer.writerow(
                {
                    "shot_id": shot["shot_id"],
                    "duration_sec": shot["duration_sec"],
                    "visual": shot["visual"],
                    "video_prompt": shot["video_prompt"],
                }
            )


def write_voice_lines(path: Path, shots: list[dict]) -> None:
    lines: list[str] = []
    for shot in shots:
        lines.append(f"{shot['shot_id']} / {shot['duration_sec']}s / {shot['voice']} / {shot['dialogue']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", nargs="?", default="episodes/ep001_moon_pink.json")
    parser.add_argument("-o", "--output-dir")
    args = parser.parse_args()

    episode = load_episode(Path(args.episode))
    output_dir = Path(args.output_dir) if args.output_dir else default_output_dir(episode)
    output_dir.mkdir(parents=True, exist_ok=True)

    shots = episode["shots"]
    image_path = output_dir / "image_prompts.csv"
    video_path = output_dir / "video_prompts.csv"
    voice_path = output_dir / "voice_lines.txt"

    write_image_prompts(image_path, shots)
    write_video_prompts(video_path, shots)
    write_voice_lines(voice_path, shots)

    print(f"Wrote {image_path}")
    print(f"Wrote {video_path}")
    print(f"Wrote {voice_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
