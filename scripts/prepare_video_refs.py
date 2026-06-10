#!/usr/bin/env python3
"""Prepare Sora input reference frames from episode storyboard images."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter, ImageOps


DEFAULT_EPISODE = Path("episodes/ep001_moon_pink.json")
DEFAULT_SIZE = "720x1280"


def load_episode(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def parse_size(value: str) -> tuple[int, int]:
    try:
        width_text, height_text = value.lower().split("x", 1)
        width = int(width_text)
        height = int(height_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("size must look like WIDTHxHEIGHT") from exc
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("size dimensions must be positive")
    return width, height


def episode_id_from(path: Path, episode: dict[str, Any]) -> str:
    value = episode.get("episode_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return path.stem


def prepare_reference_frame(source_path: Path, output_path: Path, size: tuple[int, int]) -> None:
    target_width, target_height = size
    with Image.open(source_path) as source:
        source = source.convert("RGB")
        contained = ImageOps.contain(source, size)

        background = ImageOps.fit(source, size, method=Image.Resampling.LANCZOS)
        background = background.filter(ImageFilter.GaussianBlur(radius=32))
        background = ImageOps.autocontrast(background, cutoff=1)

        x = (target_width - contained.width) // 2
        y = (target_height - contained.height) // 2
        background.paste(contained, (x, y))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    background.save(output_path, format="PNG")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", nargs="?", default=str(DEFAULT_EPISODE), help="episode JSON path")
    parser.add_argument("--images-dir", help="source storyboard image directory; defaults to assets/images/<episode_id>")
    parser.add_argument("--output-dir", help="output reference frame directory; defaults to outputs/<episode_id>/video_refs")
    parser.add_argument("--size", default=DEFAULT_SIZE, type=parse_size, help=f"target frame size, default: {DEFAULT_SIZE}")
    parser.add_argument("--force", action="store_true", help="overwrite existing reference frames")
    args = parser.parse_args()

    episode_path = Path(args.episode)
    episode = load_episode(episode_path)
    episode_id = episode_id_from(episode_path, episode)
    shots = episode.get("shots")
    if not isinstance(shots, list) or not shots:
        raise ValueError("episode JSON must contain a non-empty shots array")

    images_dir = Path(args.images_dir) if args.images_dir else Path("assets") / "images" / episode_id
    output_dir = Path(args.output_dir) if args.output_dir else Path("outputs") / episode_id / "video_refs"

    written = 0
    skipped = 0
    for shot in shots:
        shot_id = str(shot["shot_id"])
        source_path = images_dir / f"{shot_id}.png"
        output_path = output_dir / f"{shot_id}.png"
        if not source_path.exists():
            raise FileNotFoundError(f"missing source image: {source_path}")
        if output_path.exists() and not args.force:
            print(f"Skip {shot_id}: {output_path} exists")
            skipped += 1
            continue

        prepare_reference_frame(source_path, output_path, args.size)
        print(f"Wrote {output_path}")
        written += 1

    print(f"Done: written={written}, skipped={skipped}, size={args.size[0]}x{args.size[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
