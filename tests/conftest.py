from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import pytest


@pytest.fixture(scope="session")
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def sample_transcript_path(project_root: Path) -> Path:
    return project_root / "samples" / "response.json"


@pytest.fixture(scope="session")
def sample_transcript(sample_transcript_path: Path) -> Dict[str, object]:
    with sample_transcript_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="session")
def sample_tokens(sample_transcript: Dict[str, object]) -> List[dict]:
    tokens = sample_transcript.get("tokens")
    if not isinstance(tokens, list):
        raise AssertionError("Sample transcript does not contain token list.")
    return tokens
