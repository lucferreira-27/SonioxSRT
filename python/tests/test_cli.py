from __future__ import annotations

from pathlib import Path

import pytest

from sonioxsrt.cli import to_srt as to_srt_cli
from sonioxsrt.cli import transcribe as transcribe_cli


def test_to_srt_cli_main(tmp_path: Path, sample_transcript_path: Path) -> None:
    output_path = tmp_path / "subtitles.srt"
    exit_code = to_srt_cli.main(
        [
            "--input",
            str(sample_transcript_path),
            "--output",
            str(output_path),
            "--max-cpl",
            "32",
            "--line-split-delimiters",
            ".",
            "--segment-on-sentence",
        ]
    )

    assert exit_code == 0
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8").strip().splitlines()
    assert content[0] == "1"
    assert content[2] == "BBC Sounds."
    assert content[6] == "Music, radio, podcasts."


def test_transcribe_cli_requires_audio_file(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.wav"
    with pytest.raises(SystemExit):
        transcribe_cli.main(["--audio", str(missing_path)])


def test_transcribe_cli_invokes_helper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"RIFF....WAVE")
    output_path = tmp_path / "response.json"
    called = {}

    def fake_transcribe_to_file(**kwargs):
        called.update(kwargs)
        return {"id": "ok"}

    monkeypatch.setattr(transcribe_cli, "transcribe_to_file", fake_transcribe_to_file)

    exit_code = transcribe_cli.main(
        [
            "--audio",
            str(audio_path),
            "--output",
            str(output_path),
            "--model",
            "demo-model",
        ]
    )

    assert exit_code == 0
    assert called["audio_path"] == Path(audio_path)
    assert called["output_path"] == Path(output_path)
    assert called["model"] == "demo-model"


def test_to_srt_cli_translation_hook(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, sample_transcript_path: Path) -> None:
    output_path = tmp_path / "translated.srt"
    captured = {}

    def fake_translate_entries(entries, *, target_language, config, model, base_url, api_key, stats):
        stats.calls += 1
        captured["target_language"] = target_language
        captured["model"] = model
        captured["base_url"] = base_url
        captured["api_key"] = api_key
        captured["count"] = len(entries)
        captured["stats_calls"] = stats.calls
        return entries

    monkeypatch.setattr(to_srt_cli, "translate_entries", fake_translate_entries)

    exit_code = to_srt_cli.main(
        [
            "--input",
            str(sample_transcript_path),
            "--output",
            str(output_path),
            "--translate-to",
            "Spanish",
            "--llm-model",
            "demo",
            "--llm-base-url",
            "https://llm.example.com",
            "--llm-api-key",
            "secret",
        ]
    )

    assert exit_code == 0
    assert output_path.exists()
    assert captured["target_language"] == "Spanish"
    assert captured["model"] == "demo"
    assert captured["base_url"] == "https://llm.example.com"
    assert captured["api_key"] == "secret"
    assert captured["count"] > 0
    assert captured["stats_calls"] == 1


def test_to_srt_cli_translation_three_passes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, sample_transcript_path: Path) -> None:
    output_path = tmp_path / "translated.srt"
    captured = {}

    def fake_translate_entries(*_, **__):  # pragma: no cover
        raise AssertionError("translate_entries should not be called when passes=3")

    def fake_translate_entries_with_review(entries, *, target_language, config, model, base_url, api_key, stats):
        stats.calls += 3
        captured["target_language"] = target_language
        captured["model"] = model
        captured["base_url"] = base_url
        captured["api_key"] = api_key
        captured["count"] = len(entries)
        captured["stats_calls"] = stats.calls
        return entries

    monkeypatch.setattr(to_srt_cli, "translate_entries", fake_translate_entries)
    monkeypatch.setattr(
        to_srt_cli,
        "translate_entries_with_review",
        fake_translate_entries_with_review,
    )

    exit_code = to_srt_cli.main(
        [
            "--input",
            str(sample_transcript_path),
            "--output",
            str(output_path),
            "--translate-to",
            "Spanish",
            "--translation-passes",
            "3",
        ]
    )

    assert exit_code == 0
    assert output_path.exists()
    assert captured["target_language"] == "Spanish"
    assert captured["model"] is None
    assert captured["count"] > 0
    assert captured["stats_calls"] == 3
