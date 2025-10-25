from __future__ import annotations

from types import SimpleNamespace
from typing import Iterable, List

import pytest

from sonioxsrt.subtitles import SubtitleConfig, SubtitleEntry
from sonioxsrt.translation import translate_entries, translate_entries_with_review


class StubCompletions:
    def __init__(self, responses: Iterable[str]):
        self.responses = list(responses)
        self.calls: List[dict] = []
        self.index = 0

    def create(self, **kwargs):
        self.calls.append(kwargs)
        text = self.responses[self.index]
        if self.index < len(self.responses) - 1:
            self.index += 1
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
        )


class StubClient:
    def __init__(self, responses: Iterable[str]):
        self.completions = StubCompletions(responses)
        self.chat = SimpleNamespace(completions=self.completions)


def test_translate_entries_rewraps_and_preserves_indices():
    entries = [
        SubtitleEntry(index=1, start_ms=0, end_ms=1000, lines=["Hello there."]),
        SubtitleEntry(index=2, start_ms=1000, end_ms=2200, lines=["General Kenobi!"]),
    ]
    config = SubtitleConfig(max_cpl=20, max_lines=2)
    stub_client = StubClient([
        "<subtitles><line index=\"1\">Hola.</line><line index=\"2\">General Kenobi!</line></subtitles>"
    ])

    translated = translate_entries(
        entries,
        target_language="Spanish",
        config=config,
        model="demo",
        api_key="dummy",
        client=stub_client,
    )

    assert [entry.index for entry in translated] == [1, 2]
    assert translated[0].lines == ["Hola."]
    assert translated[1].lines == ["General Kenobi!"]

    assert stub_client.completions.calls
    kwargs = stub_client.completions.calls[0]
    assert kwargs["model"] == "demo"
    assert "1 Hello there." in kwargs["messages"][1]["content"]


def test_translate_entries_handles_renumbering():
    entries = [
        SubtitleEntry(index=1, start_ms=0, end_ms=1000, lines=["Hello there."]),
        SubtitleEntry(index=2, start_ms=1000, end_ms=2200, lines=["General Kenobi!"]),
    ]
    config = SubtitleConfig()
    stub_client = StubClient(
        [
            "<subtitles><line index=\"1\">Hola.</line><line index=\"2\">Hola.</line></subtitles>"
        ]
    )

    translated = translate_entries(
        entries,
        target_language="Spanish",
        config=config,
        model="demo",
        api_key="dummy",
        client=stub_client,
    )

    assert [entry.lines[0] for entry in translated] == ["Hola.", "Hola."]
    assert [entry.index for entry in translated] == [1, 2]


def test_translate_entries_raises_on_empty_response():
    entries = [
        SubtitleEntry(index=5, start_ms=0, end_ms=1000, lines=["Hello there."]),
    ]
    config = SubtitleConfig()
    stub_client = StubClient([""])

    with pytest.raises(ValueError):
        translate_entries(
            entries,
            target_language="Spanish",
            config=config,
            model="demo",
            api_key="dummy",
            client=stub_client,
        )


def test_translate_entries_chunks_large_payload():
    entries = [
        SubtitleEntry(index=1, start_ms=0, end_ms=1000, lines=["One"]),
        SubtitleEntry(index=2, start_ms=1000, end_ms=2000, lines=["Two"]),
        SubtitleEntry(index=3, start_ms=2000, end_ms=3000, lines=["Three"]),
    ]

    config = SubtitleConfig()
    stub_client = StubClient([
        "<subtitles><line index=\"1\">Uno</line><line index=\"2\">Dos</line></subtitles>",
        "<subtitles><line index=\"3\">Tres</line></subtitles>",
    ])

    translated = translate_entries(
        entries,
        target_language="Spanish",
        config=config,
        model="demo",
        api_key="dummy",
        client=stub_client,
        chunk_size=2,
    )

    assert [line for entry in translated for line in entry.lines] == [
        "Uno",
        "Dos",
        "Tres",
    ]
    assert len(stub_client.completions.calls) == 2


def test_translate_entries_uses_default_model_env(monkeypatch: pytest.MonkeyPatch):
    entries = [
        SubtitleEntry(index=1, start_ms=0, end_ms=1000, lines=["Hello"]),
    ]
    config = SubtitleConfig()
    stub_client = StubClient([
        "<subtitles><line index=\"1\">Olá</line></subtitles>"
    ])

    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setenv("DEFAULT_MODEL", "moonshotai/kimi-k2-instruct-0905")

    translate_entries(
        entries,
        target_language="Portuguese",
        config=config,
        api_key="dummy",
        client=stub_client,
    )

    assert stub_client.completions.calls
    assert (
        stub_client.completions.calls[0]["model"]
        == "moonshotai/kimi-k2-instruct-0905"
    )


def test_translate_entries_with_review_runs_three_passes():
    entries = [
        SubtitleEntry(index=1, start_ms=0, end_ms=1000, lines=["Hey."]),
        SubtitleEntry(index=2, start_ms=1000, end_ms=2200, lines=["Move on."]),
    ]
    config = SubtitleConfig()
    stub_client = StubClient(
        [
            "<subtitles><line index=\"1\">Oi.</line><line index=\"2\">Vai andando.</line></subtitles>",
            "ISSUES:\n- 2 -> sounds too literal\nSUGGESTED FIXES:\n- 2 -> Use 'Cai fora.'",
            "<subtitles><line index=\"1\">Oi.</line><line index=\"2\">Cai fora.</line></subtitles>",
        ]
    )

    result = translate_entries_with_review(
        entries,
        target_language="Portuguese",
        config=config,
        model="demo",
        api_key="dummy",
        client=stub_client,
    )

    assert [line for entry in result for line in entry.lines] == ["Oi.", "Cai fora."]
    assert len(stub_client.completions.calls) == 3

    review_call = stub_client.completions.calls[1]
    assert "ISSUES" in review_call["messages"][1]["content"]
    assert "Draft translation" in review_call["messages"][1]["content"]

    refine_call = stub_client.completions.calls[2]
    assert "Existing translation" in refine_call["messages"][1]["content"]
