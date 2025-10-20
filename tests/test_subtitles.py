from __future__ import annotations

from pathlib import Path

import pytest

from sonioxsrt.subtitles import (
    SubtitleConfig,
    extract_tokens,
    render_segments,
    srt,
    tokens_to_subtitle_segments,
    write_srt_file,
)


def test_tokens_to_subtitle_segments(sample_tokens):
    config = SubtitleConfig(max_cps=18.0, max_dur_ms=6000, min_dur_ms=800)
    segments = tokens_to_subtitle_segments(sample_tokens, config)

    assert segments, "Expected at least one subtitle segment."
    starts = [seg["start"] for seg in segments]
    ends = [seg["end"] for seg in segments]

    assert starts == sorted(starts), "Segments should be ordered by start time."
    assert all(end >= start for start, end in zip(starts, ends)), "Segment end before start."
    assert all(seg.get("tokens") for seg in segments), "Each segment should retain tokens."


def test_render_segments_and_write_srt(tmp_path: Path, sample_tokens):
    config = SubtitleConfig(max_cps=18.0, max_dur_ms=6000, max_cpl=32)
    segments = tokens_to_subtitle_segments(sample_tokens, config)
    entries = render_segments(segments, config)

    assert entries, "Rendered entries should not be empty."
    assert [entry.index for entry in entries] == list(range(1, len(entries) + 1))
    assert all(len(line) <= config.max_cpl for entry in entries for line in entry.lines)

    output = tmp_path / "output.srt"
    write_srt_file(entries, output)
    content = output.read_text(encoding="utf-8").strip().splitlines()

    assert content[0] == "1"
    assert "-->" in content[1], "SRT timestamps missing arrow."
    assert content[2], "Subtitle text should not be empty."


def test_extract_tokens_rejects_missing_tokens(tmp_path: Path):
    bad_json_path = tmp_path / "bad.json"
    bad_json_path.write_text('{"text": "hi"}', encoding="utf-8")

    import json

    with pytest.raises(ValueError):
        extract_tokens(json.loads(bad_json_path.read_text(encoding="utf-8")))


def test_srt_from_dict(tmp_path: Path, sample_transcript):
    output = tmp_path / "from_dict.srt"
    result_path = srt(sample_transcript, output_path=output)

    assert result_path == output
    assert output.exists()
    assert output.read_text(encoding="utf-8").startswith("1\n")


def test_srt_from_file(tmp_path: Path, sample_transcript_path: Path):
    output = tmp_path / "from_file.srt"
    srt(sample_transcript_path, output_path=output)

    assert output.exists()
