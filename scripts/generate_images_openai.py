#!/usr/bin/env python3
"""Generate storyboard images for a Zero-One episode with OpenAI Images."""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
import sys
import textwrap
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import urlopen

DEFAULT_EPISODE = Path("episodes/ep001_moon_pink.json")
DEFAULT_MODEL = "gpt-image-2"
DEFAULT_SIZE = "1024x1536"


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


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def style_to_prompt_text(style: object) -> str:
    if isinstance(style, str):
        return style.strip()
    if not isinstance(style, dict):
        return ""

    parts: list[str] = []
    visual_style = normalize_text(style.get("visual"))
    tone = normalize_text(style.get("tone"))
    character_rules = style.get("character_rules")
    negative_prompt = style.get("negative_prompt")

    if visual_style:
        parts.append(f"Style: {visual_style}")
    if tone:
        parts.append(f"Tone: {tone}")
    if isinstance(character_rules, list):
        rules = [normalize_text(item) for item in character_rules if normalize_text(item)]
        if rules:
            parts.append("Character rules: " + "; ".join(rules))
    if isinstance(negative_prompt, list):
        negatives = [normalize_text(item) for item in negative_prompt if normalize_text(item)]
        if negatives:
            parts.append("Avoid: " + "; ".join(negatives))

    return "\n".join(parts)


def resolve_prompt(episode: dict[str, Any], shot: dict[str, Any]) -> tuple[str, str]:
    image_prompt = normalize_text(shot.get("image_prompt"))
    if image_prompt:
        return image_prompt, "image_prompt"

    parts = [
        "Create a vertical 9:16 storyboard image.",
        normalize_text(shot.get("visual")),
        normalize_text(shot.get("character_action")),
        style_to_prompt_text(episode.get("style")),
    ]
    prompt = "\n".join(part for part in parts if part)
    if not prompt:
        raise ValueError(f"{shot.get('shot_id', '<unknown>')} has no prompt fields")
    return prompt, "fallback_visual_character_action_style"


def relative_display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def write_prompts_used(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def make_openai_client() -> Any:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Set it in your shell or a local .env file before running this script."
        )

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Missing dependency: install requirements with `pip install -r requirements.txt`.") from exc

    return OpenAI()


def require_pillow() -> None:
    try:
        import PIL  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("Missing dependency: install requirements with `pip install -r requirements.txt`.") from exc


def image_bytes_from_response(response: Any) -> bytes:
    data = getattr(response, "data", None)
    if not data:
        raise RuntimeError("OpenAI image response did not include data.")

    first = data[0]
    image_base64 = getattr(first, "b64_json", None)
    if image_base64:
        return base64.b64decode(image_base64)

    image_url = getattr(first, "url", None)
    if image_url:
        with urlopen(image_url, timeout=120) as response_file:
            return response_file.read()

    raise RuntimeError("OpenAI image response did not include b64_json or url image data.")


def generate_image(client: Any, *, model: str, size: str, prompt: str, quality: str | None) -> bytes:
    request: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "size": size,
    }
    if quality:
        request["quality"] = quality

    response = client.images.generate(**request)
    return image_bytes_from_response(response)


def generate_image_with_references(
    client: Any,
    *,
    model: str,
    size: str,
    prompt: str,
    quality: str | None,
    reference_images: list[Path],
) -> bytes:
    request: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "size": size,
    }
    if quality:
        request["quality"] = quality

    with ExitStack() as stack:
        request["image"] = [stack.enter_context(path.open("rb")) for path in reference_images]
        response = client.images.edit(**request)
    return image_bytes_from_response(response)


def build_reference_prompt(prompt: str, reference_images: list[Path]) -> str:
    if not reference_images:
        return prompt

    return "\n".join(
        [
            "Use the provided reference image(s) only as the character identity anchor for Zero-One.",
            "For this episode, Zero-One must match the S02 reference identity: pale-haired chibi AI queen, half-lidded cool expression, black-and-gold sci-fi styling, mechanical tentacles, floating crown, and mechanical throne energy.",
            "Keep the shot's action, setting, and story beat from the prompt below. Do not copy the exact S02 composition unless the shot calls for it.",
            "Do not use the older design-sheet helmet look in this rerun.",
            "",
            prompt,
        ]
    )


def save_contact_sheet(image_paths: list[Path], output_path: Path) -> None:
    from PIL import Image, ImageDraw, ImageOps

    existing_paths = [path for path in image_paths if path.exists()]
    if not existing_paths:
        print("No images found for contact sheet; skipped.")
        return

    thumb_width = 240
    thumb_height = 360
    label_height = 32
    padding = 16
    columns = min(5, max(1, math.ceil(math.sqrt(len(existing_paths)))))
    rows = math.ceil(len(existing_paths) / columns)

    sheet_width = columns * thumb_width + (columns + 1) * padding
    sheet_height = rows * (thumb_height + label_height) + (rows + 1) * padding
    sheet = Image.new("RGB", (sheet_width, sheet_height), "white")
    draw = ImageDraw.Draw(sheet)

    for index, image_path in enumerate(existing_paths):
        row = index // columns
        column = index % columns
        x = padding + column * (thumb_width + padding)
        y = padding + row * (thumb_height + label_height + padding)

        with Image.open(image_path) as image:
            thumbnail = ImageOps.contain(image.convert("RGB"), (thumb_width, thumb_height))
        offset_x = x + (thumb_width - thumbnail.width) // 2
        offset_y = y + label_height + (thumb_height - thumbnail.height) // 2
        sheet.paste(thumbnail, (offset_x, offset_y))

        label = image_path.stem
        draw.text((x, y), label, fill=(32, 32, 32))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, format="JPEG", quality=92)


def build_prompt_payload(
    *,
    episode_id: str,
    model: str,
    size: str,
    quality: str | None,
    reference_images: list[Path],
    shot_ids: set[str] | None,
    prompt_records: list[dict[str, Any]],
) -> dict[str, Any]:
    payload = {
        "episode_id": episode_id,
        "model": model,
        "size": size,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prompts": prompt_records,
    }
    if quality:
        payload["quality"] = quality
    if reference_images:
        payload["reference_images"] = [relative_display_path(path) for path in reference_images]
    if shot_ids:
        payload["shot_ids"] = sorted(shot_ids)
    return payload


def parse_non_negative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--limit must be a non-negative integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("--limit must be a non-negative integer")
    return parsed


def parse_shot_ids(value: str | None) -> set[str] | None:
    if not value:
        return None

    shot_ids = {item.strip() for item in value.split(",") if item.strip()}
    if not shot_ids:
        raise argparse.ArgumentTypeError("--shot-ids must contain at least one shot id")
    bad_ids = sorted(shot_id for shot_id in shot_ids if len(shot_id) != 3 or not shot_id.startswith("s") or not shot_id[1:].isdigit())
    if bad_ids:
        raise argparse.ArgumentTypeError("--shot-ids values must look like s02,s03; bad values: " + ", ".join(bad_ids))
    return shot_ids


def resolve_reference_images(values: list[str]) -> list[Path]:
    paths = [Path(value) for value in values]
    missing = [path for path in paths if not path.exists()]
    if missing:
        missing_text = ", ".join(path.as_posix() for path in missing)
        raise FileNotFoundError(f"reference image not found: {missing_text}")
    return paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """\
            Examples:
              python scripts/generate_images_openai.py
              python scripts/generate_images_openai.py --limit 1
              python scripts/generate_images_openai.py --force
              python scripts/generate_images_openai.py episodes/ep001_moon_pink.json --model gpt-image-2
            """
        ),
    )
    parser.add_argument("episode", nargs="?", default=str(DEFAULT_EPISODE), help="episode JSON path")
    parser.add_argument("--images-dir", help="directory for generated PNGs; defaults to assets/images/<episode_id>")
    parser.add_argument("--output-dir", help="directory for prompt log and contact sheet; defaults to outputs/<episode_id>")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"OpenAI image model, default: {DEFAULT_MODEL}")
    parser.add_argument("--size", default=DEFAULT_SIZE, help=f"image size, default: {DEFAULT_SIZE}")
    parser.add_argument("--quality", choices=["low", "medium", "high", "auto"], help="optional image quality")
    parser.add_argument("--shot-ids", type=parse_shot_ids, help="comma-separated shot ids to generate, for example: s03,s04")
    parser.add_argument(
        "--reference-image",
        action="append",
        default=[],
        help="reference image path; can be supplied multiple times",
    )
    parser.add_argument("--force", action="store_true", help="overwrite existing images")
    parser.add_argument(
        "--limit",
        type=parse_non_negative_int,
        help="maximum images to actually generate this run; skipped existing images do not count",
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv_if_available()
    args = parse_args()

    episode_path = Path(args.episode)
    episode = load_episode(episode_path)
    episode_id = episode_id_from(episode_path, episode)
    shots = episode.get("shots")
    if not isinstance(shots, list) or not shots:
        raise ValueError("episode JSON must contain a non-empty shots array")
    reference_images = resolve_reference_images(args.reference_image)

    images_dir = Path(args.images_dir) if args.images_dir else Path("assets") / "images" / episode_id
    output_dir = Path(args.output_dir) if args.output_dir else Path("outputs") / episode_id
    prompts_path = output_dir / "image_prompts_used.json"
    contact_sheet_path = output_dir / "contact_sheet.jpg"
    images_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    prompt_records: list[dict[str, Any]] = []
    image_paths: list[Path] = []

    for index, shot in enumerate(shots, start=1):
        if not isinstance(shot, dict):
            raise ValueError(f"shots[{index}] must be an object")
        shot_id = normalize_text(shot.get("shot_id")) or f"s{index:02d}"
        prompt, prompt_source = resolve_prompt(episode, shot)
        is_selected = args.shot_ids is None or shot_id in args.shot_ids
        if is_selected:
            prompt = build_reference_prompt(prompt, reference_images)
            if reference_images:
                prompt_source += "+reference_images"
        image_path = images_dir / f"{shot_id}.png"
        image_paths.append(image_path)
        prompt_records.append(
            {
                "shot_id": shot_id,
                "image_path": relative_display_path(image_path),
                "prompt_source": prompt_source,
                "prompt": prompt,
                "status": "pending",
            }
        )

    prompt_payload = build_prompt_payload(
        episode_id=episode_id,
        model=args.model,
        size=args.size,
        quality=args.quality,
        reference_images=reference_images,
        shot_ids=args.shot_ids,
        prompt_records=prompt_records,
    )

    require_pillow()
    limit_allows_generation = args.limit is None or args.limit > 0
    needs_generation = limit_allows_generation and any(
        (args.shot_ids is None or record["shot_id"] in args.shot_ids) and (args.force or not image_path.exists())
        for record, image_path in zip(prompt_records, image_paths)
    )
    client = make_openai_client() if needs_generation else None
    write_prompts_used(prompts_path, prompt_payload)

    generated_count = 0
    for record, image_path in zip(prompt_records, image_paths):
        shot_id = record["shot_id"]
        if args.shot_ids is not None and shot_id not in args.shot_ids:
            record["status"] = "skipped_shot_filter"
            print(f"Skip {shot_id}: not selected by --shot-ids")
            write_prompts_used(prompts_path, prompt_payload)
            continue
        if image_path.exists() and not args.force:
            record["status"] = "skipped_existing"
            print(f"Skip {shot_id}: {relative_display_path(image_path)} exists")
            write_prompts_used(prompts_path, prompt_payload)
            continue
        if args.limit is not None and generated_count >= args.limit:
            record["status"] = "skipped_limit"
            print(f"Skip {shot_id}: generation limit reached")
            write_prompts_used(prompts_path, prompt_payload)
            continue

        try:
            print(f"Generate {shot_id}: {relative_display_path(image_path)}")
            if client is None:
                raise RuntimeError("OpenAI client was not initialized.")
            if reference_images:
                image_bytes = generate_image_with_references(
                    client,
                    model=args.model,
                    size=args.size,
                    prompt=record["prompt"],
                    quality=args.quality,
                    reference_images=reference_images,
                )
            else:
                image_bytes = generate_image(
                    client,
                    model=args.model,
                    size=args.size,
                    prompt=record["prompt"],
                    quality=args.quality,
                )
            image_path.write_bytes(image_bytes)
            record["status"] = "generated"
            generated_count += 1
        except Exception as exc:
            record["status"] = "error"
            record["error"] = str(exc)
            write_prompts_used(prompts_path, prompt_payload)
            raise

        write_prompts_used(prompts_path, prompt_payload)

    save_contact_sheet(image_paths, contact_sheet_path)
    print(f"Wrote {relative_display_path(prompts_path)}")
    print(f"Wrote {relative_display_path(contact_sheet_path)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Image generation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
