"""CLI for submitting audio to Soniox and saving the JSON transcript."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from ..api import DEFAULT_BASE_URL, DEFAULT_POLL_INTERVAL, SonioxError
from ..transcriber import transcribe_to_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Submit audio to Soniox and save the JSON transcript."
    )
    parser.add_argument(
        "--audio",
        default="audio.wav",
        help="Path to the local audio file to transcribe (default: audio.wav).",
    )
    parser.add_argument(
        "--audio-url",
        help="Optional public URL of the audio file instead of --audio.",
    )
    parser.add_argument(
        "--model",
        default="stt-async-preview",
        help="Soniox model to use (default: stt-async-preview).",
    )
    parser.add_argument(
        "--output",
        default="response.json",
        help="Path to save the JSON response (default: response.json).",
    )
    parser.add_argument(
        "--keep-resources",
        action="store_true",
        help="Skip deleting the uploaded file and transcription on Soniox.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL,
        help=(
            f"Seconds between status polls (default: {DEFAULT_POLL_INTERVAL}). "
            "Lower values poll more frequently."
        ),
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Override the Soniox API base URL (default: {DEFAULT_BASE_URL}).",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.audio_url and not Path(args.audio).exists():
        parser.error(f"Audio file not found: {args.audio}")

    try:
        transcribe_to_file(
            audio_path=None if args.audio_url else Path(args.audio),
            audio_url=args.audio_url,
            model=args.model,
            output_path=Path(args.output),
            poll_interval=args.poll_interval,
            keep_remote=args.keep_resources,
            base_url=args.base_url,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1
    except SonioxError as exc:
        print(exc, file=sys.stderr)
        return 1

    print(f"Saved transcription JSON to {args.output}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
