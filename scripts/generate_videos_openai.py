#!/usr/bin/env python3
"""Generate per-shot videos for a Zero-One episode with OpenAI Videos."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_EPISODE = Path("episodes/ep001_moon_pink.json")
DEFAULT_MODEL = "sora-2"
DEFAULT_SIZE = "720x1280"
DEFAULT_SECONDS = "8"
DONE_STATUSES = {"completed", "succeeded"}
FAILED_STATUSES = {"failed", "cancelled", "canceled", "expired"}


def load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


def load_episode(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def episode_id_from(path: Path, episode: dict[str, Any]) -> str:
    value = episode.get("episode_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return path.stem


def make_openai_client() -> Any:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set. Set it in your shell or a local .env file.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Missing dependency: install requirements with `pip install -r requirements.txt`.") from exc
    return OpenAI(timeout=600.0)


def parse_shot_ids(value: str | None) -> set[str] | None:
    if not value:
        return None
    shot_ids = {item.strip() for item in value.split(",") if item.strip()}
    if not shot_ids:
        raise argparse.ArgumentTypeError("--shot-ids must contain at least one shot id")
    bad_ids = sorted(shot_id for shot_id in shot_ids if len(shot_id) != 3 or not shot_id.startswith("s") or not shot_id[1:].isdigit())
    if bad_ids:
        raise argparse.ArgumentTypeError("--shot-ids values must look like s01,s02; bad values: " + ", ".join(bad_ids))
    return shot_ids


def object_to_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    return {"repr": repr(value)}


def get_attr(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def save_binary_response(response: Any, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(response, "write_to_file"):
        response.write_to_file(output_path)
        return
    if hasattr(response, "content"):
        output_path.write_bytes(response.content)
        return
    if hasattr(response, "read"):
        output_path.write_bytes(response.read())
        return
    raise RuntimeError("Could not save binary OpenAI response.")


def load_jobs(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"jobs": []}
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_jobs(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def find_existing_job(payload: dict[str, Any], shot_id: str) -> dict[str, Any] | None:
    for record in payload.get("jobs", []):
        if record.get("shot_id") == shot_id:
            return record
    return None


def build_video_prompt(shot: dict[str, Any]) -> str:
    return "\n".join(
        [
            "Create a vertical animated short video from the provided reference frame.",
            "Preserve the image's character identity, visual style, composition, palette, and story continuity.",
            "Use subtle cinematic motion, parallax, screen/UI movement, character micro-expressions, and light effects. Avoid sudden redesigns, scene cuts, extra characters, logos, or subtitles burned into the video.",
            f"Shot action: {shot['video_prompt']}",
            f"Dialogue beat: {shot['dialogue']}",
            f"Target edit duration after trimming: {shot['duration_sec']} seconds.",
        ]
    )


def create_video_job(client: Any, *, model: str, size: str, seconds: str, prompt: str, reference_path: Path) -> Any:
    with reference_path.open("rb") as reference_file:
        return client.videos.create(
            model=model,
            size=size,
            seconds=seconds,
            prompt=prompt,
            input_reference=(reference_path.name, reference_file, "image/png"),
        )


def wait_for_video(client: Any, video_id: str, *, poll_interval: int, timeout_sec: int) -> Any:
    started_at = time.monotonic()
    last_status = None
    while True:
        video = client.videos.retrieve(video_id)
        status = str(get_attr(video, "status", "")).lower()
        if status != last_status:
            print(f"Video {video_id}: {status}")
            last_status = status
        if status in DONE_STATUSES or status in FAILED_STATUSES:
            return video
        if time.monotonic() - started_at > timeout_sec:
            raise TimeoutError(f"timed out waiting for video {video_id}; last status={status}")
        time.sleep(poll_interval)


def main() -> int:
    load_dotenv_if_available()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", nargs="?", default=str(DEFAULT_EPISODE), help="episode JSON path")
    parser.add_argument("--refs-dir", help="input reference frames; defaults to outputs/<episode_id>/video_refs")
    parser.add_argument("--clips-dir", help="output clips directory; defaults to outputs/<episode_id>/clips")
    parser.add_argument("--jobs", help="jobs JSON path; defaults to outputs/<episode_id>/video_jobs.json")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"video model, default: {DEFAULT_MODEL}")
    parser.add_argument("--size", default=DEFAULT_SIZE, choices=["720x1280", "1280x720", "1024x1792", "1792x1024"])
    parser.add_argument("--seconds", default=DEFAULT_SECONDS, choices=["4", "8", "12"], help=f"generated clip length, default: {DEFAULT_SECONDS}")
    parser.add_argument("--shot-ids", type=parse_shot_ids, help="comma-separated shot ids to generate")
    parser.add_argument("--poll-interval", type=int, default=15, help="seconds between status polls")
    parser.add_argument("--timeout-sec", type=int, default=1800, help="per-shot wait timeout")
    parser.add_argument("--force", action="store_true", help="regenerate and overwrite existing clips")
    args = parser.parse_args()

    episode_path = Path(args.episode)
    episode = load_episode(episode_path)
    episode_id = episode_id_from(episode_path, episode)
    shots = episode.get("shots")
    if not isinstance(shots, list) or not shots:
        raise ValueError("episode JSON must contain a non-empty shots array")

    refs_dir = Path(args.refs_dir) if args.refs_dir else Path("outputs") / episode_id / "video_refs"
    clips_dir = Path(args.clips_dir) if args.clips_dir else Path("outputs") / episode_id / "clips"
    jobs_path = Path(args.jobs) if args.jobs else Path("outputs") / episode_id / "video_jobs.json"

    selected_shots = [shot for shot in shots if args.shot_ids is None or shot["shot_id"] in args.shot_ids]
    if not selected_shots:
        raise ValueError("no shots selected")

    client = make_openai_client()
    jobs_payload = load_jobs(jobs_path)
    jobs_payload.update(
        {
            "episode_id": episode_id,
            "model": args.model,
            "size": args.size,
            "seconds": args.seconds,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    failures: list[str] = []
    for shot in selected_shots:
        shot_id = shot["shot_id"]
        reference_path = refs_dir / f"{shot_id}.png"
        output_path = clips_dir / f"{shot_id}.mp4"
        if not reference_path.exists():
            raise FileNotFoundError(f"missing video reference frame: {reference_path}")
        if output_path.exists() and not args.force:
            print(f"Skip {shot_id}: {output_path} exists")
            continue

        prompt = build_video_prompt(shot)
        record = find_existing_job(jobs_payload, shot_id)
        if record is None:
            record = {"shot_id": shot_id}
            jobs_payload.setdefault("jobs", []).append(record)

        try:
            print(f"Create video {shot_id}: {output_path}")
            video = create_video_job(
                client,
                model=args.model,
                size=args.size,
                seconds=args.seconds,
                prompt=prompt,
                reference_path=reference_path,
            )
            video_id = get_attr(video, "id")
            if not video_id:
                raise RuntimeError("video create response did not include an id")

            record.update(
                {
                    "status": get_attr(video, "status", "created"),
                    "video_id": video_id,
                    "prompt": prompt,
                    "reference_path": reference_path.as_posix(),
                    "clip_path": output_path.as_posix(),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "response": object_to_dict(video),
                }
            )
            write_jobs(jobs_path, jobs_payload)

            video = wait_for_video(client, video_id, poll_interval=args.poll_interval, timeout_sec=args.timeout_sec)
            status = str(get_attr(video, "status", "")).lower()
            record.update(
                {
                    "status": status,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "response": object_to_dict(video),
                }
            )
            if status not in DONE_STATUSES:
                record["error"] = object_to_dict(get_attr(video, "error", {}))
                failures.append(shot_id)
                write_jobs(jobs_path, jobs_payload)
                continue

            response = client.videos.download_content(video_id, variant="video")
            save_binary_response(response, output_path)
            record["status"] = "downloaded"
            record["downloaded_at"] = datetime.now(timezone.utc).isoformat()
            write_jobs(jobs_path, jobs_payload)
            print(f"Wrote {output_path}")
        except Exception as exc:
            record["status"] = "error"
            record["error"] = str(exc)
            record["updated_at"] = datetime.now(timezone.utc).isoformat()
            write_jobs(jobs_path, jobs_payload)
            failures.append(shot_id)
            print(f"Video generation failed for {shot_id}: {exc}", file=sys.stderr)

    if failures:
        print("Failed shots: " + ", ".join(failures), file=sys.stderr)
        return 1
    print(f"Wrote {jobs_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
