"""Orchestration helpers for Soniox transcription workflows."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .api import (
    DEFAULT_BASE_URL,
    DEFAULT_POLL_INTERVAL,
    SonioxClient,
    SonioxError,
    require_api_key,
)

LOGGER = logging.getLogger(__name__)


def _ensure_client(
    client: Optional[SonioxClient],
    *,
    base_url: Optional[str] = None,
) -> Tuple[SonioxClient, bool]:
    if client is not None:
        return client, False
    api_key = require_api_key()
    created = SonioxClient(api_key=api_key, base_url=base_url or DEFAULT_BASE_URL)
    return created, True


def transcribe_audio(
    *,
    audio_path: Optional[Path | str] = None,
    audio_url: Optional[str] = None,
    model: str = "stt-async-preview",
    extra_options: Optional[Dict[str, Any]] = None,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    keep_remote: bool = False,
    client: Optional[SonioxClient] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    if not audio_path and not audio_url:
        raise ValueError("Specify either audio_path or audio_url.")

    resolved_audio_path: Optional[Path] = None
    if audio_path is not None:
        resolved_audio_path = Path(audio_path)
        if not resolved_audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {resolved_audio_path}")

    soniox_client, owns_client = _ensure_client(client, base_url=base_url)
    file_id: Optional[str] = None
    transcription_id: Optional[str] = None

    try:
        if resolved_audio_path is not None:
            LOGGER.info("Uploading audio file %s", resolved_audio_path)
            file_id = soniox_client.upload_file(str(resolved_audio_path))

        LOGGER.info(
            "Creating transcription job (model=%s, file_id=%s, audio_url=%s)",
            model,
            file_id,
            audio_url,
        )
        transcription_id = soniox_client.create_transcription(
            model=model,
            file_id=file_id,
            audio_url=audio_url,
            extra_options=extra_options,
        )
        LOGGER.info("Waiting for transcription %s to complete", transcription_id)
        soniox_client.wait_for_completion(
            transcription_id, poll_interval=poll_interval
        )
        LOGGER.info("Fetching transcript %s", transcription_id)
        transcript = soniox_client.fetch_transcript(transcription_id)
        return transcript
    finally:
        if not keep_remote:
            if transcription_id:
                try:
                    LOGGER.info("Deleting remote transcription %s", transcription_id)
                    soniox_client.delete_transcription(transcription_id)
                except SonioxError as exc:
                    LOGGER.warning("Failed to delete transcription %s: %s", transcription_id, exc)
            if file_id:
                try:
                    LOGGER.info("Deleting uploaded file %s", file_id)
                    soniox_client.delete_file(file_id)
                except SonioxError as exc:
                    LOGGER.warning("Failed to delete file %s: %s", file_id, exc)
        if owns_client:
            soniox_client.close()


def transcribe_audio_file(
    audio_path: Path | str,
    *,
    model: str = "stt-async-preview",
    extra_options: Optional[Dict[str, Any]] = None,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    keep_remote: bool = False,
    client: Optional[SonioxClient] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    return transcribe_audio(
        audio_path=audio_path,
        model=model,
        extra_options=extra_options,
        poll_interval=poll_interval,
        keep_remote=keep_remote,
        client=client,
        base_url=base_url,
    )


def transcribe_audio_url(
    audio_url: str,
    *,
    model: str = "stt-async-preview",
    extra_options: Optional[Dict[str, Any]] = None,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    keep_remote: bool = False,
    client: Optional[SonioxClient] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    return transcribe_audio(
        audio_url=audio_url,
        model=model,
        extra_options=extra_options,
        poll_interval=poll_interval,
        keep_remote=keep_remote,
        client=client,
        base_url=base_url,
    )


def transcribe_to_file(
    *,
    output_path: Path | str,
    audio_path: Optional[Path | str] = None,
    audio_url: Optional[str] = None,
    model: str = "stt-async-preview",
    extra_options: Optional[Dict[str, Any]] = None,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    keep_remote: bool = False,
    client: Optional[SonioxClient] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    transcript = transcribe_audio(
        audio_path=audio_path,
        audio_url=audio_url,
        model=model,
        extra_options=extra_options,
        poll_interval=poll_interval,
        keep_remote=keep_remote,
        client=client,
        base_url=base_url,
    )
    output = Path(output_path)
    LOGGER.info("Writing transcript JSON to %s", output)
    output.write_text(
        json.dumps(transcript, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return transcript


__all__ = [
    "transcribe_audio",
    "transcribe_audio_file",
    "transcribe_audio_url",
    "transcribe_to_file",
]
