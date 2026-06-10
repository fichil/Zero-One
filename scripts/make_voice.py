#!/usr/bin/env python3
"""Prepare a voiceover script without invoking a TTS provider."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_episode(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def default_output_path(episode: dict) -> Path:
    episode_id = episode["episode_id"].lower()
    return Path("outputs") / episode_id / "voiceover_script.txt"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", nargs="?", default="episodes/ep001_moon_pink.json")
    parser.add_argument("-o", "--output")
    args = parser.parse_args()

    episode = load_episode(Path(args.episode))
    output_path = Path(args.output) if args.output else default_output_path(episode)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    content = (
        f"{episode['episode_id']} {episode['title']}\n"
        f"Duration: {episode['duration_seconds']} seconds\n"
        "TTS status: pending provider integration. This file is script-only.\n\n"
        f"{episode['voiceover']['script'].strip()}\n"
    )
    output_path.write_text(content, encoding="utf-8")
    print(f"Wrote {output_path}")
    print("TTS pending: no audio file was generated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
