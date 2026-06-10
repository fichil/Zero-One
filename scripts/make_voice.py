#!/usr/bin/env python3
"""Prepare a per-voice dialogue script without invoking a TTS provider."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_episode(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def default_output_path(episode: dict) -> Path:
    return Path("outputs") / episode["episode_id"] / "voiceover_script.txt"


def build_voice_script(episode: dict) -> str:
    lines = [
        f"{episode['episode_id']} {episode['title']}",
        f"Duration: {episode['duration_target_sec']} seconds",
        "TTS status: pending provider integration. This file is script-only.",
        "",
    ]
    for shot in episode["shots"]:
        lines.append(f"[{shot['voice']}] {shot['shot_id']} / {shot['duration_sec']}s")
        lines.append(shot["dialogue"].strip())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", nargs="?", default="episodes/ep001_moon_pink.json")
    parser.add_argument("-o", "--output")
    args = parser.parse_args()

    episode = load_episode(Path(args.episode))
    output_path = Path(args.output) if args.output else default_output_path(episode)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(build_voice_script(episode), encoding="utf-8")
    voices = sorted({shot["voice"] for shot in episode["shots"]})
    print(f"Wrote {output_path}")
    print("Voices: " + ", ".join(voices))
    print("TTS pending: no audio file was generated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
