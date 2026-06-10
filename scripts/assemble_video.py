#!/usr/bin/env python3
"""Create an editing manifest without assembling video media."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


K_SHOT_ID = "\u955c\u5934\u7f16\u53f7"
K_DURATION = "\u65f6\u957f\u79d2"


VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}


def load_episode(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def find_clip(shot_id: str, search_dirs: list[Path]) -> str | None:
    for directory in search_dirs:
        if not directory.exists():
            continue
        for path in sorted(directory.iterdir()):
            if path.is_file() and path.stem.lower().startswith(shot_id.lower()) and path.suffix.lower() in VIDEO_EXTENSIONS:
                return str(path)
    return None


def default_output_path(episode: dict) -> Path:
    episode_id = episode["episode_id"].lower()
    return Path("outputs") / episode_id / "editing_manifest.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", nargs="?", default="episodes/ep001_moon_pink.json")
    parser.add_argument("-o", "--output")
    args = parser.parse_args()

    episode = load_episode(Path(args.episode))
    output_path = Path(args.output) if args.output else default_output_path(episode)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    episode_dir = Path("outputs") / episode["episode_id"].lower()
    search_dirs = [Path("assets/clips"), episode_dir]
    clips = []
    missing = []
    for shot in episode["storyboard"]["shots"]:
        shot_id = shot[K_SHOT_ID]
        clip = find_clip(shot_id, search_dirs)
        clips.append(
            {
                "shot_id": shot_id,
                "duration_seconds": shot[K_DURATION],
                "clip": clip,
                "status": "ready" if clip else "missing",
            }
        )
        if clip is None:
            missing.append(shot_id)

    manifest = {
        "episode_id": episode["episode_id"],
        "title": episode["title"],
        "duration_seconds": episode["duration_seconds"],
        "status": "ready_for_assembly" if not missing else "waiting_for_clips",
        "missing_clips": missing,
        "clips": clips,
        "note": "This manifest does not assemble video. Add per-shot clips to assets/clips or outputs/ep001.",
    }
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output_path}")
    if missing:
        print("Missing clips: " + ", ".join(missing))
    else:
        print("All clips found. External assembly tool can consume the manifest.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
