#!/usr/bin/env python3
"""Generate per-shot voiceover audio for a Zero-One episode with OpenAI TTS."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_EPISODE = Path("episodes/ep001_moon_pink.json")
DEFAULT_MODEL = "gpt-4o-mini-tts"
DEFAULT_FORMAT = "mp3"
DEFAULT_VOICES = {
    "narrator": "alloy",
    "zero_one": "coral",
    "crowd": "echo",
    "robot_002": "ash",
}
DEFAULT_INSTRUCTIONS = {
    "narrator": "Speak Mandarin Chinese with a crisp, amused documentary narrator tone. Keep the delivery dry and concise.",
    "zero_one": "Speak Mandarin Chinese as a lazy but powerful AI queen: cool, half-lidded, deadpan, slightly smug, not overly energetic.",
    "crowd": "Speak Mandarin Chinese as surprised background humans. Keep it natural, short, and comedic.",
    "robot_002": "Speak Mandarin Chinese as an anxious secretary robot. Make it urgent but still cute and clean.",
}


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
    return OpenAI(timeout=180.0)


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


def parse_voice_override(values: list[str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise argparse.ArgumentTypeError("--voice values must look like role=voice")
        role, voice = value.split("=", 1)
        role = role.strip()
        voice = voice.strip()
        if not role or not voice:
            raise argparse.ArgumentTypeError("--voice values must look like role=voice")
        overrides[role] = voice
    return overrides


def object_to_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    return {"repr": repr(value)}


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"audio": []}
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def find_record(payload: dict[str, Any], shot_id: str) -> dict[str, Any] | None:
    for record in payload.get("audio", []):
        if record.get("shot_id") == shot_id:
            return record
    return None


def main() -> int:
    load_dotenv_if_available()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", nargs="?", default=str(DEFAULT_EPISODE), help="episode JSON path")
    parser.add_argument("--output-dir", help="output audio directory; defaults to outputs/<episode_id>/audio")
    parser.add_argument("--manifest", help="voice manifest path; defaults to outputs/<episode_id>/voice_jobs.json")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"TTS model, default: {DEFAULT_MODEL}")
    parser.add_argument("--response-format", default=DEFAULT_FORMAT, choices=["mp3", "opus", "aac", "flac", "wav", "pcm"])
    parser.add_argument("--voice", action="append", default=[], help="override a role voice, for example: zero_one=coral")
    parser.add_argument("--force", action="store_true", help="regenerate and overwrite existing audio")
    args = parser.parse_args()

    episode_path = Path(args.episode)
    episode = load_episode(episode_path)
    episode_id = episode_id_from(episode_path, episode)
    shots = episode.get("shots")
    if not isinstance(shots, list) or not shots:
        raise ValueError("episode JSON must contain a non-empty shots array")

    output_dir = Path(args.output_dir) if args.output_dir else Path("outputs") / episode_id / "audio"
    manifest_path = Path(args.manifest) if args.manifest else Path("outputs") / episode_id / "voice_jobs.json"
    voices = {**DEFAULT_VOICES, **parse_voice_override(args.voice)}
    client = make_openai_client()

    manifest = load_manifest(manifest_path)
    manifest.update(
        {
            "episode_id": episode_id,
            "model": args.model,
            "response_format": args.response_format,
            "voices": voices,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    failures: list[str] = []
    for shot in shots:
        shot_id = shot["shot_id"]
        role = shot["voice"]
        voice = voices.get(role, "alloy")
        output_path = output_dir / f"{shot_id}_{role}.{args.response_format}"
        if output_path.exists() and not args.force:
            print(f"Skip {shot_id}: {output_path} exists")
            continue

        record = find_record(manifest, shot_id)
        if record is None:
            record = {"shot_id": shot_id}
            manifest.setdefault("audio", []).append(record)

        try:
            print(f"Generate voice {shot_id}: {output_path}")
            response = client.audio.speech.create(
                model=args.model,
                voice=voice,
                input=shot["dialogue"],
                instructions=DEFAULT_INSTRUCTIONS.get(role, "Speak Mandarin Chinese clearly and naturally."),
                response_format=args.response_format,
            )
            save_binary_response(response, output_path)
            record.update(
                {
                    "status": "generated",
                    "shot_id": shot_id,
                    "voice_role": role,
                    "voice": voice,
                    "text": shot["dialogue"],
                    "audio_path": output_path.as_posix(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            write_manifest(manifest_path, manifest)
        except Exception as exc:
            record.update(
                {
                    "status": "error",
                    "shot_id": shot_id,
                    "voice_role": role,
                    "voice": voice,
                    "text": shot["dialogue"],
                    "error": str(exc),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            write_manifest(manifest_path, manifest)
            failures.append(shot_id)
            print(f"Voice generation failed for {shot_id}: {exc}", file=sys.stderr)

    if failures:
        print("Failed shots: " + ", ".join(failures), file=sys.stderr)
        return 1
    print(f"Wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
