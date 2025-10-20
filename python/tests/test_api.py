from __future__ import annotations

import os
from pathlib import Path

import pytest

from sonioxsrt.api import require_api_key


def test_require_api_key_reads_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env_file = tmp_path / ".env"
    env_file.write_text("SONIOX_API_KEY=test-from-file\nOTHER=1\n", encoding="utf-8")
    monkeypatch.delenv("SONIOX_API_KEY", raising=False)

    api_key = require_api_key(search_paths=[env_file])

    assert api_key == "test-from-file"
    assert os.environ["SONIOX_API_KEY"] == "test-from-file"

    monkeypatch.delenv("SONIOX_API_KEY", raising=False)
