#!/usr/bin/env python3
"""Assemble generated clips, voiceover, and subtitles into a final episode MP4."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


DEFAULT_EPISODE = Path("episodes/ep001_moon_pink.json")
DEFAULT_SIZE = "720x1280"
VIDEO_EXTENSIONS = [".mp4", ".mov", ".m4v", ".webm"]
AUDIO_EXTENSIONS = [".mp3", ".wav", ".m4a", ".aac", ".flac", ".opus"]


def load_episode(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def episode_id_from(path: Path, episode: dict[str, Any]) -> str:
    value = episode.get("episode_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return path.stem


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


def ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError("Missing dependency: install requirements with `pip install -r requirements.txt`.") from exc
    return imageio_ffmpeg.get_ffmpeg_exe()


def run_ffmpeg(args: list[str]) -> None:
    print("ffmpeg " + " ".join(args[1:]))
    result = subprocess.run(args, check=False, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        if result.stdout.strip():
            print(result.stdout)
        if result.stderr.strip():
            print(result.stderr)
        raise RuntimeError(f"ffmpeg failed with exit code {result.returncode}")


def find_video_clip(clips_dir: Path, shot_id: str) -> Path:
    if not clips_dir.exists():
        raise FileNotFoundError(f"missing clips directory: {clips_dir}; run generate_videos_openai.py first")
    for extension in VIDEO_EXTENSIONS:
        candidate = clips_dir / f"{shot_id}{extension}"
        if candidate.exists():
            return candidate
    matches = [path for path in clips_dir.iterdir() if path.is_file() and path.stem.lower().startswith(shot_id.lower()) and path.suffix.lower() in VIDEO_EXTENSIONS]
    if matches:
        return sorted(matches)[0]
    raise FileNotFoundError(f"missing video clip for {shot_id} in {clips_dir}")


def find_audio_clip(audio_dir: Path, shot_id: str, role: str) -> Path | None:
    if not audio_dir.exists():
        return None
    for extension in AUDIO_EXTENSIONS:
        candidate = audio_dir / f"{shot_id}_{role}{extension}"
        if candidate.exists():
            return candidate
    matches = [path for path in audio_dir.iterdir() if path.is_file() and path.stem.lower().startswith(f"{shot_id}_") and path.suffix.lower() in AUDIO_EXTENSIONS]
    if matches:
        return sorted(matches)[0]
    return None


def escape_concat_path(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "'\\''")


def subtitle_filter_path(path: Path) -> str:
    # A relative POSIX-like path avoids Windows drive-letter escaping in ffmpeg filters.
    return path.as_posix().replace("\\", "/").replace("'", r"\'").replace(":", r"\:")


def make_segment(
    *,
    ffmpeg: str,
    shot: dict[str, Any],
    clip_path: Path,
    audio_path: Path | None,
    output_path: Path,
    size: tuple[int, int],
) -> None:
    width, height = size
    duration = str(shot["duration_sec"])
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        "setsar=1,format=yuv420p"
    )

    if audio_path is None:
        command = [
            ffmpeg,
            "-y",
            "-i",
            str(clip_path),
            "-f",
            "lavfi",
            "-t",
            duration,
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
        ]
    else:
        command = [
            ffmpeg,
            "-y",
            "-i",
            str(clip_path),
            "-i",
            str(audio_path),
        ]

    command.extend(
        [
            "-t",
            duration,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-vf",
            vf,
            "-af",
            f"apad,atrim=0:{duration},asetpts=PTS-STARTPTS",
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-threads",
            "1",
            "-preset",
            "ultrafast",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(command)


def concat_segments(*, ffmpeg: str, segments: list[Path], list_path: Path, output_path: Path) -> None:
    list_path.parent.mkdir(parents=True, exist_ok=True)
    list_path.write_text(
        "\n".join(f"file '{escape_concat_path(path)}'" for path in segments) + "\n",
        encoding="utf-8",
    )
    run_ffmpeg(
        [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c",
            "copy",
            str(output_path),
        ]
    )


def burn_subtitles(*, ffmpeg: str, input_path: Path, subtitles_path: Path, output_path: Path) -> None:
    filter_value = (
        f"subtitles='{subtitle_filter_path(subtitles_path)}':"
        "force_style='FontName=Microsoft YaHei,FontSize=18,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,"
        "Alignment=2,MarginV=120'"
    )
    run_ffmpeg(
        [
            ffmpeg,
            "-y",
            "-i",
            str(input_path),
            "-vf",
            filter_value,
            "-c:v",
            "libx264",
            "-threads",
            "1",
            "-preset",
            "ultrafast",
            "-crf",
            "18",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", nargs="?", default=str(DEFAULT_EPISODE), help="episode JSON path")
    parser.add_argument("--clips-dir", help="generated video clips directory; defaults to outputs/<episode_id>/clips")
    parser.add_argument("--audio-dir", help="generated audio directory; defaults to outputs/<episode_id>/audio")
    parser.add_argument("--subtitles", help="SRT subtitles path; defaults to outputs/<episode_id>/<episode_id>_subtitles.srt")
    parser.add_argument("--output", help="final MP4 path; defaults to outputs/<episode_id>/final/<episode_id>_final.mp4")
    parser.add_argument("--work-dir", help="temporary assembly directory; defaults to outputs/<episode_id>/final/work")
    parser.add_argument("--size", default=DEFAULT_SIZE, type=parse_size, help=f"final video size, default: {DEFAULT_SIZE}")
    parser.add_argument("--no-subtitles", action="store_true", help="do not burn subtitles into the final video")
    parser.add_argument("--allow-missing-audio", action="store_true", help="use silence for shots with missing audio")
    parser.add_argument("--keep-work", action="store_true", help="keep intermediate segment files")
    args = parser.parse_args()

    episode_path = Path(args.episode)
    episode = load_episode(episode_path)
    episode_id = episode_id_from(episode_path, episode)
    shots = episode.get("shots")
    if not isinstance(shots, list) or not shots:
        raise ValueError("episode JSON must contain a non-empty shots array")

    clips_dir = Path(args.clips_dir) if args.clips_dir else Path("outputs") / episode_id / "clips"
    audio_dir = Path(args.audio_dir) if args.audio_dir else Path("outputs") / episode_id / "audio"
    subtitles_path = Path(args.subtitles) if args.subtitles else Path("outputs") / episode_id / f"{episode_id}_subtitles.srt"
    final_path = Path(args.output) if args.output else Path("outputs") / episode_id / "final" / f"{episode_id}_final.mp4"
    work_dir = Path(args.work_dir) if args.work_dir else Path("outputs") / episode_id / "final" / "work"
    temp_concat_path = work_dir / f"{episode_id}_concat.mp4"

    ffmpeg = ffmpeg_exe()
    segments: list[Path] = []
    for shot in shots:
        shot_id = shot["shot_id"]
        clip_path = find_video_clip(clips_dir, shot_id)
        audio_path = find_audio_clip(audio_dir, shot_id, shot["voice"])
        if audio_path is None and not args.allow_missing_audio:
            raise FileNotFoundError(f"missing audio for {shot_id} in {audio_dir}")

        segment_path = work_dir / "segments" / f"{shot_id}.mp4"
        make_segment(
            ffmpeg=ffmpeg,
            shot=shot,
            clip_path=clip_path,
            audio_path=audio_path,
            output_path=segment_path,
            size=args.size,
        )
        segments.append(segment_path)

    concat_segments(ffmpeg=ffmpeg, segments=segments, list_path=work_dir / "concat.txt", output_path=temp_concat_path)

    final_path.parent.mkdir(parents=True, exist_ok=True)
    if args.no_subtitles or not subtitles_path.exists():
        shutil.copy2(temp_concat_path, final_path)
        print(f"Wrote {final_path}")
    else:
        burn_subtitles(ffmpeg=ffmpeg, input_path=temp_concat_path, subtitles_path=subtitles_path, output_path=final_path)
        print(f"Wrote {final_path}")

    if not args.keep_work:
        shutil.rmtree(work_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
