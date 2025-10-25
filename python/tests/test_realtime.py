"""Unit tests for realtime transcription helpers."""

from sonioxsrt.realtime import (
    RealTimeResult,
    build_realtime_config,
    render_tokens,
)


def test_build_realtime_config_accepts_preview_v2_model() -> None:
    config = build_realtime_config(
        api_key="dummy",
        model="stt-rt-preview-v2",
        audio_format="auto",
        language_hints=["en", "es"],
        enable_language_identification=True,
        enable_speaker_diarization=True,
        context="Example context",
    )

    assert config["model"] == "stt-rt-preview-v2"
    assert config["audio_format"] == "auto"
    assert config["language_hints"] == ["en", "es"]
    assert config["enable_language_identification"] is True
    assert config["enable_speaker_diarization"] is True
    assert "context" in config


def test_render_tokens_renders_speaker_and_language_tags() -> None:
    final_tokens = [
        {"text": "Hello", "is_final": True, "speaker": "A", "language": "en"},
    ]
    non_final_tokens = [
        {
            "text": " mundo",
            "is_final": False,
            "language": "es",
            "translation_status": "translation",
        }
    ]

    rendered = render_tokens(final_tokens, non_final_tokens)

    assert "Speaker A:" in rendered
    assert "[en]" in rendered
    assert "[Translation] [es]" in rendered
    assert rendered.endswith("===============================")


def test_realtime_result_to_transcript() -> None:
    result = RealTimeResult(
        model="stt-rt-preview-v2",
        final_tokens=[
            {"text": "Hello", "is_final": True},
            {"text": " world", "is_final": True},
        ],
        responses=[{"sequence_id": 1}],
    )

    transcript = result.to_transcript()
    assert transcript["model"] == "stt-rt-preview-v2"
    assert transcript["tokens"] == result.final_tokens
    assert transcript["responses"] == [{"sequence_id": 1}]
    assert transcript["text"].strip().startswith("Hello")
