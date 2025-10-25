"""High-level helpers for Soniox transcription workflows."""

from .api import (
    DEFAULT_BASE_URL,
    DEFAULT_POLL_INTERVAL,
    SonioxClient,
    SonioxError,
    require_api_key,
)
from .transcriber import (
    transcribe_audio,
    transcribe_audio_file,
    transcribe_audio_url,
    transcribe_to_file,
)
from .realtime import (
    DEFAULT_REALTIME_MODEL,
    RealTimeDependencyError,
    RealTimeResult,
    RealTimeUpdate,
    SONIOX_REALTIME_URL,
    SUPPORTED_REALTIME_MODELS,
    build_realtime_config,
    render_tokens as render_realtime_tokens,
    run_realtime_session,
)
from .subtitles import (
    SubtitleConfig,
    SubtitleEntry,
    extract_tokens,
    render_segments,
    srt,
    tokens_to_subtitle_segments,
    write_srt_file,
)
from .translation import (
    LLM_API_KEY_ENV,
    LLM_BASE_URL_ENV,
    LLM_MODEL_ENV,
    DEFAULT_MODEL_ENV,
    translate_entries,
    translate_entries_with_review,
    TranslationStats,
)

__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_POLL_INTERVAL",
    "DEFAULT_REALTIME_MODEL",
    "SonioxClient",
    "SonioxError",
    "SONIOX_REALTIME_URL",
    "SubtitleConfig",
    "SubtitleEntry",
    "require_api_key",
    "extract_tokens",
    "render_realtime_tokens",
    "render_segments",
    "srt",
    "run_realtime_session",
    "translate_entries",
    "translate_entries_with_review",
    "TranslationStats",
    "build_realtime_config",
    "transcribe_audio",
    "transcribe_audio_file",
    "transcribe_audio_url",
    "transcribe_to_file",
    "tokens_to_subtitle_segments",
    "RealTimeDependencyError",
    "RealTimeUpdate",
    "RealTimeResult",
    "SUPPORTED_REALTIME_MODELS",
    "write_srt_file",
    "LLM_API_KEY_ENV",
    "LLM_BASE_URL_ENV",
    "LLM_MODEL_ENV",
    "DEFAULT_MODEL_ENV",
]
