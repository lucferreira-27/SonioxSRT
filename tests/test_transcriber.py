from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from sonioxsrt import transcriber
from sonioxsrt.transcriber import (
    transcribe_audio,
    transcribe_audio_file,
    transcribe_audio_url,
    transcribe_to_file,
)


class DummyClient:
    def __init__(self, transcript: Dict[str, Any]) -> None:
        self.transcript = transcript
        self.uploaded_path: Optional[str] = None
        self.transcription_id = "tx-1"
        self.closed = False
        self.deleted_transcription: Optional[str] = None
        self.deleted_file: Optional[str] = None
        self.waited_for: Optional[str] = None
        self.model_used: Optional[str] = None
        self.extra_options: Optional[Dict[str, Any]] = None
        self.audio_url_seen: Optional[str] = None

    def upload_file(self, audio_path: str) -> str:
        self.uploaded_path = audio_path
        return "file-1"

    def create_transcription(
        self,
        *,
        model: str,
        file_id: Optional[str] = None,
        audio_url: Optional[str] = None,
        extra_options: Optional[Dict[str, Any]] = None,
    ) -> str:
        self.model_used = model
        self.extra_options = extra_options
        self.audio_url_seen = audio_url
        return self.transcription_id

    def wait_for_completion(self, transcription_id: str, *, poll_interval: float) -> None:
        self.waited_for = transcription_id

    def fetch_transcript(self, transcription_id: str) -> Dict[str, Any]:
        return self.transcript

    def delete_transcription(self, transcription_id: str) -> None:
        self.deleted_transcription = transcription_id

    def delete_file(self, file_id: str) -> None:
        self.deleted_file = file_id

    def close(self) -> None:
        self.closed = True


@pytest.fixture()
def dummy_client(sample_transcript: Dict[str, Any]) -> DummyClient:
    return DummyClient(sample_transcript)


def _patch_client(monkeypatch: pytest.MonkeyPatch, dummy: DummyClient, own_client: bool = True) -> None:
    def fake_ensure_client(client=None, *, base_url=None):
        if client is not None:
            return client, False
        return dummy, own_client

    monkeypatch.setattr(transcriber, "_ensure_client", fake_ensure_client)


def test_transcribe_audio_file(tmp_path: Path, dummy_client: DummyClient, monkeypatch: pytest.MonkeyPatch):
    audio_path = tmp_path / "clip.wav"
    audio_path.write_bytes(b"RIFF....WAVE")
    _patch_client(monkeypatch, dummy_client)

    result = transcribe_audio_file(audio_path=audio_path, client=None)

    assert result == dummy_client.transcript
    assert dummy_client.uploaded_path == str(audio_path)
    assert dummy_client.waited_for == dummy_client.transcription_id
    assert dummy_client.deleted_transcription == dummy_client.transcription_id
    assert dummy_client.deleted_file == "file-1"
    assert dummy_client.closed is True


def test_transcribe_audio_url(monkeypatch: pytest.MonkeyPatch, dummy_client: DummyClient):
    _patch_client(monkeypatch, dummy_client)
    result = transcribe_audio_url(audio_url="https://example.com/audio.mp3", client=None, keep_remote=True)

    assert result == dummy_client.transcript
    assert dummy_client.uploaded_path is None, "Uploading should not occur for audio URLs."
    assert dummy_client.audio_url_seen == "https://example.com/audio.mp3"
    assert dummy_client.deleted_transcription is None, "Resources retained when keep_remote=True."


def test_transcribe_to_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dummy_client: DummyClient):
    output_path = tmp_path / "response.json"
    _patch_client(monkeypatch, dummy_client)

    result = transcribe_to_file(audio_url="https://example.com/audio.mp3", output_path=output_path)

    assert json.loads(output_path.read_text(encoding="utf-8")) == dummy_client.transcript
    assert result == dummy_client.transcript


def test_transcribe_audio_requires_input(monkeypatch: pytest.MonkeyPatch):
    with pytest.raises(ValueError):
        transcribe_audio()
