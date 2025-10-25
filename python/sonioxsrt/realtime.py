"""Real-time transcription helpers for the Soniox WebSocket API."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from .api import require_api_key

try:  # Optional dependency that is only required for realtime streaming.
    from websockets import ConnectionClosedError, ConnectionClosedOK  # type: ignore
    from websockets.sync.client import ClientConnection, connect  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - handled at runtime in helpers.
    ConnectionClosedError = ConnectionClosedOK = None  # type: ignore
    ClientConnection = None  # type: ignore
    connect = None  # type: ignore

SONIOX_REALTIME_URL = "wss://stt-rt.soniox.com/transcribe-websocket"
DEFAULT_REALTIME_MODEL = "stt-rt-preview"
SUPPORTED_REALTIME_MODELS = (
    DEFAULT_REALTIME_MODEL,
    "stt-rt-preview-v2",
)
DEFAULT_AUDIO_CHUNK_SIZE = 3840
DEFAULT_AUDIO_SLEEP_SECONDS = 0.120


class RealTimeDependencyError(RuntimeError):
    """Raised when realtime helpers are used without the websockets package."""


def _ensure_websockets_available() -> None:
    if connect is None:
        raise RealTimeDependencyError(
            "Missing dependency: websockets\n"
            "Install it with 'pip install websockets>=11' to use realtime features."
        )


def render_tokens(
    final_tokens: Sequence[Dict[str, Any]],
    non_final_tokens: Sequence[Dict[str, Any]],
) -> str:
    """Render a human-readable transcript from realtime tokens."""
    text_parts: List[str] = []
    current_speaker: Optional[str] = None
    current_language: Optional[str] = None

    for token in [*final_tokens, *non_final_tokens]:
        text = token.get("text")
        if not text:
            continue
        speaker = token.get("speaker")
        language = token.get("language")
        is_translation = token.get("translation_status") == "translation"

        if speaker and speaker != current_speaker:
            if current_speaker is not None:
                text_parts.append("\n\n")
            current_speaker = speaker
            current_language = None
            text_parts.append(f"Speaker {current_speaker}:")

        if language and language != current_language:
            current_language = language
            prefix = "[Translation] " if is_translation else ""
            text_parts.append(f"\n{prefix}[{current_language}] ")
            text = text.lstrip()

        text_parts.append(text)

    if text_parts:
        text_parts.append("\n===============================")

    return "".join(text_parts)


def build_realtime_config(
    *,
    api_key: str,
    model: str = DEFAULT_REALTIME_MODEL,
    audio_format: str = "auto",
    sample_rate: Optional[int] = None,
    num_channels: Optional[int] = None,
    language_hints: Optional[Sequence[str]] = None,
    enable_language_identification: bool = False,
    enable_speaker_diarization: bool = False,
    context: Optional[str] = None,
    enable_endpoint_detection: Optional[bool] = True,
    translation: Optional[Dict[str, Any] | str] = None,
    extra_options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a config payload accepted by the realtime WebSocket API."""
    config: Dict[str, Any] = {
        "api_key": api_key,
        "model": model,
    }

    if language_hints:
        config["language_hints"] = list(language_hints)
    if enable_language_identification:
        config["enable_language_identification"] = True
    if enable_speaker_diarization:
        config["enable_speaker_diarization"] = True
    if context:
        config["context"] = context
    if enable_endpoint_detection is not None:
        config["enable_endpoint_detection"] = bool(enable_endpoint_detection)

    if audio_format == "auto":
        config["audio_format"] = "auto"
    else:
        config["audio_format"] = audio_format
        if sample_rate is not None:
            config["sample_rate"] = sample_rate
        if num_channels is not None:
            config["num_channels"] = num_channels

    if translation:
        if isinstance(translation, str):
            if translation != "none":
                raise ValueError(
                    "translation string must be 'none' or provide a dict with options."
                )
        else:
            config["translation"] = translation

    if extra_options:
        config.update(extra_options)

    return config


def _stream_audio(
    audio_path: Path,
    ws: ClientConnection,
    *,
    chunk_size: int,
    sleep_seconds: float,
) -> None:
    """Send audio bytes over the websocket, simulating realtime pacing."""
    with audio_path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            ws.send(chunk)
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
    ws.send("")  # Empty string signals end-of-audio.


@dataclass
class RealTimeUpdate:
    """Represents a single realtime response update."""

    text: str
    final_tokens: List[Dict[str, Any]]
    non_final_tokens: List[Dict[str, Any]]
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RealTimeResult:
    """Holds the aggregated realtime transcription outcome."""

    model: str
    final_tokens: List[Dict[str, Any]]
    responses: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return render_tokens(self.final_tokens, ())

    def to_transcript(self) -> Dict[str, Any]:
        """Return a transcript-like payload compatible with subtitle helpers."""
        return {
            "model": self.model,
            "tokens": self.final_tokens,
            "responses": self.responses,
            "text": self.text,
        }


def run_realtime_session(
    audio_path: Path | str,
    *,
    api_key: Optional[str] = None,
    model: str = DEFAULT_REALTIME_MODEL,
    audio_format: str = "auto",
    sample_rate: Optional[int] = None,
    num_channels: Optional[int] = None,
    language_hints: Optional[Sequence[str]] = None,
    enable_language_identification: bool = False,
    enable_speaker_diarization: bool = False,
    context: Optional[str] = None,
    enable_endpoint_detection: Optional[bool] = True,
    translation: Optional[Dict[str, Any] | str] = None,
    extra_options: Optional[Dict[str, Any]] = None,
    websocket_url: str = SONIOX_REALTIME_URL,
    chunk_size: int = DEFAULT_AUDIO_CHUNK_SIZE,
    chunk_sleep: float = DEFAULT_AUDIO_SLEEP_SECONDS,
    on_update: Optional[Callable[[RealTimeUpdate], None]] = None,
) -> RealTimeResult:
    """Stream audio to the realtime API and return the aggregated result."""
    _ensure_websockets_available()

    if not isinstance(audio_path, Path):
        audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    if api_key is None:
        api_key = require_api_key()

    config = build_realtime_config(
        api_key=api_key,
        model=model,
        audio_format=audio_format,
        sample_rate=sample_rate,
        num_channels=num_channels,
        language_hints=language_hints,
        enable_language_identification=enable_language_identification,
        enable_speaker_diarization=enable_speaker_diarization,
        context=context,
        enable_endpoint_detection=enable_endpoint_detection,
        translation=translation,
        extra_options=extra_options,
    )

    final_tokens: List[Dict[str, Any]] = []
    responses: List[Dict[str, Any]] = []

    with connect(websocket_url) as ws:  # type: ignore[arg-type]
        ws.send(json.dumps(config))
        streamer = threading.Thread(
            target=_stream_audio,
            args=(audio_path, ws),
            kwargs={"chunk_size": chunk_size, "sleep_seconds": chunk_sleep},
            daemon=True,
        )
        streamer.start()

        try:
            while True:
                message = ws.recv()
                if not isinstance(message, (bytes, str)):
                    continue
                payload = json.loads(message)
                responses.append(payload)

                error_code = payload.get("error_code")
                if error_code is not None:
                    error_message = payload.get("error_message", "unknown error")
                    raise RuntimeError(f"Realtime session error {error_code}: {error_message}")

                non_final_tokens: List[Dict[str, Any]] = []
                for token in payload.get("tokens", []):
                    text = token.get("text")
                    if not text:
                        continue
                    if token.get("is_final"):
                        final_tokens.append(token)
                    else:
                        non_final_tokens.append(token)

                update_text = render_tokens(final_tokens, non_final_tokens)
                if on_update:
                    on_update(
                        RealTimeUpdate(
                            text=update_text,
                            final_tokens=list(final_tokens),
                            non_final_tokens=non_final_tokens,
                            raw=payload,
                        )
                    )

                if payload.get("finished"):
                    break
        except (ConnectionClosedOK, ConnectionClosedError):
            # Expected when the server closes the socket after finished=True.
            pass
        finally:
            streamer.join(timeout=1.0)

    return RealTimeResult(model=model, final_tokens=final_tokens, responses=responses)


__all__ = [
    "DEFAULT_REALTIME_MODEL",
    "DEFAULT_AUDIO_CHUNK_SIZE",
    "DEFAULT_AUDIO_SLEEP_SECONDS",
    "RealTimeDependencyError",
    "RealTimeResult",
    "RealTimeUpdate",
    "SUPPORTED_REALTIME_MODELS",
    "build_realtime_config",
    "render_tokens",
    "run_realtime_session",
    "SONIOX_REALTIME_URL",
]
