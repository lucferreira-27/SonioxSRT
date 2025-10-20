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
from .subtitles import (
    SubtitleConfig,
    SubtitleEntry,
    extract_tokens,
    render_segments,
    srt,
    tokens_to_subtitle_segments,
    write_srt_file,
)

__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_POLL_INTERVAL",
    "SonioxClient",
    "SonioxError",
    "SubtitleConfig",
    "SubtitleEntry",
    "require_api_key",
    "extract_tokens",
    "render_segments",
    "srt",
    "transcribe_audio",
    "transcribe_audio_file",
    "transcribe_audio_url",
    "transcribe_to_file",
    "tokens_to_subtitle_segments",
    "write_srt_file",
]
