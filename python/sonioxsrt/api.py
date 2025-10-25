"""Core Soniox API client utilities."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence

try:  # Optional dependency for loading environment variables from .env files
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - handled at runtime if dependency missing
    load_dotenv = None

try:
    import requests
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency: requests\nInstall it with 'pip install requests' and retry."
    ) from exc


DEFAULT_BASE_URL = "https://api.soniox.com"
DEFAULT_POLL_INTERVAL = 1.0


class SonioxError(Exception):
    """Raised when the Soniox API returns an unexpected status or payload."""


def _load_env_file(path: Path) -> None:
    if load_dotenv is not None:
        load_dotenv(dotenv_path=path, override=False)
        return
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:  # pragma: no cover
        return
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _candidate_env_paths(extra_paths: Optional[Sequence[Path]]) -> Iterable[Path]:
    seen: set[Path] = set()
    if extra_paths:
        for p in extra_paths:
            resolved = Path(p).resolve()
            if resolved not in seen:
                seen.add(resolved)
                yield resolved

    cwd_env = Path.cwd() / ".env"
    if cwd_env.resolve() not in seen:
        seen.add(cwd_env.resolve())
        yield cwd_env

    package_root = Path(__file__).resolve().parents[1]
    for candidate in (
        package_root / ".env",
        package_root.parent / ".env",
    ):
        resolved = candidate.resolve()
        if resolved not in seen:
            seen.add(resolved)
            yield candidate


def require_api_key(
    env_var: str = "SONIOX_API_KEY",
    *,
    search_paths: Optional[Sequence[Path]] = None,
) -> str:
    """Fetch the Soniox API key from the environment or exit with instructions."""
    api_key = os.environ.get(env_var)
    if not api_key:
        for env_path in _candidate_env_paths(search_paths):
            if env_path.is_file():
                _load_env_file(env_path)
                api_key = os.environ.get(env_var)
                if api_key:
                    break
        if not api_key:
            raise SystemExit(
                f"{env_var} is not set.\n"
                "Create an API key in the Soniox Console and export it:\n"
                f"  export {env_var}=<YOUR_API_KEY>"
            )
    return api_key


@dataclass
class SonioxClient:
    """Lightweight Soniox API client wrapping a requests session."""

    api_key: str
    base_url: str = DEFAULT_BASE_URL
    session: requests.Session = field(default_factory=requests.Session)

    def __post_init__(self) -> None:
        self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})

    # --- Resource management -------------------------------------------------
    def close(self) -> None:
        """Close the underlying HTTP session."""
        self.session.close()

    # --- File handling -------------------------------------------------------
    def upload_file(self, audio_path: str) -> str:
        with open(audio_path, "rb") as audio_file:
            response = self.session.post(
                f"{self.base_url}/v1/files", files={"file": audio_file}
            )
        if response.status_code not in (200, 201, 202):
            raise SonioxError(f"File upload failed: {response.text}")
        payload = response.json()
        file_id = payload.get("id")
        if not file_id:
            raise SonioxError(f"Unexpected upload response: {payload}")
        return file_id

    def delete_file(self, file_id: str) -> None:
        response = self.session.delete(f"{self.base_url}/v1/files/{file_id}")
        if response.status_code not in (200, 204):
            raise SonioxError(
                f"Failed to delete file {file_id}: {response.text}"
            )

    # --- Transcription handling ---------------------------------------------
    def create_transcription(
        self,
        *,
        model: str,
        file_id: Optional[str] = None,
        audio_url: Optional[str] = None,
        extra_options: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not file_id and not audio_url:
            raise ValueError("Specify either file_id or audio_url.")
        payload: Dict[str, Any] = {"model": model}
        if file_id:
            payload["file_id"] = file_id
        if audio_url:
            payload["audio_url"] = audio_url
        if extra_options:
            payload.update(extra_options)

        response = self.session.post(
            f"{self.base_url}/v1/transcriptions", json=payload
        )
        if response.status_code not in (200, 201, 202):
            raise SonioxError(f"Create transcription failed: {response.text}")
        transcription_id = response.json().get("id")
        if not transcription_id:
            raise SonioxError(
                f"Unexpected transcription response: {response.json()}"
            )
        return transcription_id

    def wait_for_completion(
        self,
        transcription_id: str,
        *,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ) -> None:
        status_url = f"{self.base_url}/v1/transcriptions/{transcription_id}"
        while True:
            response = self.session.get(status_url)
            if response.status_code != 200:
                raise SonioxError(f"Polling failed: {response.text}")
            payload = response.json()
            status = payload.get("status")
            if status == "completed":
                return
            if status == "error":
                message = payload.get("error_message") or "unknown error"
                raise SonioxError(f"Transcription failed: {message}")
            time.sleep(poll_interval)

    def fetch_transcript(self, transcription_id: str) -> Dict[str, Any]:
        response = self.session.get(
            f"{self.base_url}/v1/transcriptions/{transcription_id}/transcript"
        )
        if response.status_code != 200:
            raise SonioxError(f"Fetching transcript failed: {response.text}")
        return response.json()

    def delete_transcription(self, transcription_id: str) -> None:
        response = self.session.delete(
            f"{self.base_url}/v1/transcriptions/{transcription_id}"
        )
        if response.status_code not in (200, 204):
            raise SonioxError(
                f"Failed to delete transcription {transcription_id}: {response.text}"
            )


__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_POLL_INTERVAL",
    "SonioxClient",
    "SonioxError",
    "require_api_key",
]
