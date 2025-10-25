"""CLI for converting Soniox transcripts to SRT subtitles."""

from __future__ import annotations

import argparse
import json
import logging
import os
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
from ..translation import (
    LLM_API_KEY_ENV,
    LLM_BASE_URL_ENV,
    LLM_MODEL_ENV,
    DEFAULT_MODEL_ENV,
    translate_entries,
    translate_entries_with_review,
    TranslationStats,
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
        "--line-split-delimiters",
        default="",
        help=(
            "Prefer splitting subtitle lines after these characters when wrapping. "
            "Example: '.' or '.!?'."
        ),
    )
    parser.add_argument(
        "--segment-on-sentence",
        dest="segment_on_sentence",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_CONFIG.segment_on_sentence,
        help=(
            "End subtitle entries at sentence-ending punctuation even without long silences. "
            "Use --no-segment-on-sentence to disable."
        ),
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
    parser.add_argument(
        "--translate-to",
        help=(
            "Translate the subtitles to the specified language using an OpenAI-compatible LLM. "
            f"Requires {LLM_API_KEY_ENV} in the environment or --llm-api-key."
        ),
    )
    parser.add_argument(
        "--translation-passes",
        type=int,
        choices=(1, 3),
        default=1,
        help="Number of translation passes to run (1=draft only, 3=draft/review/refine).",
    )
    parser.add_argument(
        "--llm-model",
        default=os.environ.get(LLM_MODEL_ENV) or os.environ.get(DEFAULT_MODEL_ENV),
        help=(
            "Model name for translation (default: environment variable "
            f"{LLM_MODEL_ENV}, then {DEFAULT_MODEL_ENV}, or gpt-4o-mini)."
        ),
    )
    parser.add_argument(
        "--llm-base-url",
        default=os.environ.get(LLM_BASE_URL_ENV),
        help=(
            "Override the translation LLM base URL (default: environment variable "
            f"{LLM_BASE_URL_ENV})."
        ),
    )
    parser.add_argument(
        "--llm-api-key",
        default=os.environ.get(LLM_API_KEY_ENV),
        help=(
            "API key for the translation LLM (default: environment variable "
            f"{LLM_API_KEY_ENV} or .env)."
        ),
    )
    return parser


def _configure_logging() -> None:
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    else:
        root.setLevel(logging.INFO)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    _configure_logging()
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

    line_split_delimiters = tuple(
        ch for ch in args.line_split_delimiters if not ch.isspace()
    )

    config = SubtitleConfig(
        gap_ms=args.gap_ms,
        min_dur_ms=args.min_dur_ms,
        max_dur_ms=args.max_dur_ms,
        max_cps=args.max_cps,
        max_cpl=args.max_cpl,
        max_lines=args.max_lines,
        line_split_delimiters=line_split_delimiters,
        segment_on_sentence=args.segment_on_sentence,
        split_on_speaker=args.split_on_speaker,
        ellipses=args.ellipses,
    )

    segments = tokens_to_subtitle_segments(tokens, config)
    if not segments:
        print("No subtitle segments were produced from the tokens.", file=sys.stderr)
        return 1

    entries = render_segments(segments, config)

    if args.translate_to:
        try:
            stats = TranslationStats()
            translate_fn = (
                translate_entries_with_review
                if args.translation_passes == 3
                else translate_entries
            )
            entries = translate_fn(
                entries,
                target_language=args.translate_to,
                config=config,
                model=args.llm_model,
                base_url=args.llm_base_url,
                api_key=args.llm_api_key,
                stats=stats,
            )
            print(
                f"LLM usage: prompts={stats.prompt_tokens} completion={stats.completion_tokens}"
                f" total={stats.total_tokens} tokens across {stats.calls} calls"
            )
        except Exception as exc:  # pragma: no cover - safeguard for CLI usage
            print(f"Translation failed: {exc}", file=sys.stderr)
            return 1

    write_srt_file(entries, Path(args.output))
    print(f"Wrote {len(entries)} subtitles to {args.output}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
