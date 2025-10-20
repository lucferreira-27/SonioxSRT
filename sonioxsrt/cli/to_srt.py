"""CLI for converting Soniox transcripts to SRT subtitles."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from ..subtitles import (
    SubtitleConfig,
    extract_tokens,
    render_segments,
    tokens_to_subtitle_segments,
    write_srt_file,
)

DEFAULT_CONFIG = SubtitleConfig()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert a Soniox transcription JSON into an SRT subtitle file."
    )
    parser.add_argument(
        "--input",
        default="response.json",
        help="Path to the Soniox JSON transcript (default: response.json).",
    )
    parser.add_argument(
        "--output",
        default="subtitles.srt",
        help="Path for the generated SRT file (default: subtitles.srt).",
    )
    parser.add_argument(
        "--gap-ms",
        type=int,
        default=DEFAULT_CONFIG.gap_ms,
        help="Start new subtitles when silence between tokens exceeds this gap (default: 1200).",
    )
    parser.add_argument(
        "--min-dur-ms",
        type=int,
        default=DEFAULT_CONFIG.min_dur_ms,
        help="Minimum subtitle duration in milliseconds (default: 1000).",
    )
    parser.add_argument(
        "--max-dur-ms",
        type=int,
        default=DEFAULT_CONFIG.max_dur_ms,
        help="Maximum subtitle duration in milliseconds (default: 7000).",
    )
    parser.add_argument(
        "--max-cps",
        type=float,
        default=DEFAULT_CONFIG.max_cps,
        help="Maximum characters-per-second for readability (default: 17).",
    )
    parser.add_argument(
        "--max-cpl",
        type=int,
        default=DEFAULT_CONFIG.max_cpl,
        help="Maximum characters per line when wrapping (default: 42).",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=DEFAULT_CONFIG.max_lines,
        help="Maximum number of lines per subtitle (default: 2).",
    )
    parser.add_argument(
        "--split-on-speaker",
        action="store_true",
        help="Start a new subtitle on speaker changes.",
    )
    parser.add_argument(
        "--ellipses",
        action="store_true",
        help="Use ellipses (…) to mark continued sentences across subtitles.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    if not input_path.exists():
        parser.error(f"Input file not found: {input_path}")

    try:
        transcript = json.loads(input_path.read_text(encoding="utf-8"))
        tokens = extract_tokens(transcript)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1

    config = SubtitleConfig(
        gap_ms=args.gap_ms,
        min_dur_ms=args.min_dur_ms,
        max_dur_ms=args.max_dur_ms,
        max_cps=args.max_cps,
        max_cpl=args.max_cpl,
        max_lines=args.max_lines,
        split_on_speaker=args.split_on_speaker,
        ellipses=args.ellipses,
    )

    segments = tokens_to_subtitle_segments(tokens, config)
    if not segments:
        print("No subtitle segments were produced from the tokens.", file=sys.stderr)
        return 1

    entries = render_segments(segments, config)
    write_srt_file(entries, Path(args.output))
    print(f"Wrote {len(entries)} subtitles to {args.output}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
