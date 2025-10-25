"""Utilities for translating subtitle entries via OpenAI-compatible LLMs."""

from __future__ import annotations

import os
import re
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape

from .api import require_api_key
from .subtitles import SubtitleConfig, SubtitleEntry


LLM_API_KEY_ENV = "LLM_API_KEY"
LLM_MODEL_ENV = "LLM_MODEL"
DEFAULT_MODEL_ENV = "DEFAULT_MODEL"
LLM_BASE_URL_ENV = "LLM_BASE_URL"

_LINE_PATTERN = re.compile(r"^(?P<index>\d+)[\s\.:\-)]+(?P<text>.*)$")
DEFAULT_CHUNK_SIZE = 200
MAX_TRANSLATION_RETRIES = 2


LOGGER = logging.getLogger(__name__)


@dataclass
class TranslationStats:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0
    per_stage: Dict[str, int] = field(default_factory=dict)

    def record(self, stage: str, usage: Optional[object]) -> None:
        if not usage:
            return
        prompt = getattr(usage, "prompt_tokens", None)
        completion = getattr(usage, "completion_tokens", None)
        total = getattr(usage, "total_tokens", None)
        if prompt is None and completion is None and total is None:
            return
        if prompt is not None:
            self.prompt_tokens += int(prompt)
        if completion is not None:
            self.completion_tokens += int(completion)
        if total is not None:
            self.total_tokens += int(total)
        else:
            self.total_tokens += int(prompt or 0) + int(completion or 0)
        self.calls += 1
        self.per_stage[stage] = self.per_stage.get(stage, 0) + 1


def _format_entries(entries: Sequence[SubtitleEntry]) -> str:
    lines: List[str] = []
    for entry in entries:
        text = " ".join(line.strip() for line in entry.lines if line.strip()).strip()
        if not text:
            continue
        lines.append(f"{entry.index} {text}")
    return "\n".join(lines)


def _format_entries_xml(entries: Sequence[SubtitleEntry]) -> str:
    parts: List[str] = ["<subtitles>"]
    for entry in entries:
        text = " ".join(line.strip() for line in entry.lines if line.strip()).strip()
        escaped_text = escape(text)
        parts.append(f"  <line index=\"{entry.index}\">{escaped_text}</line>")
    parts.append("</subtitles>")
    return "\n".join(parts)


def _parse_translated_lines(
    translated: str, expected_indices: Iterable[int]
) -> Dict[int, str]:
    xml_mapping = _parse_xml_lines(translated)
    if xml_mapping is not None:
        return xml_mapping

    ordered_pairs: List[tuple[int, str]] = []
    mapping: Dict[int, str] = {}
    current_index: Optional[int] = None

    for raw_line in translated.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _LINE_PATTERN.match(line)
        if match:
            current_index = int(match.group("index"))
            text = match.group("text").strip()
            mapping[current_index] = text
            ordered_pairs.append((current_index, text))
        elif current_index is not None:
            mapping[current_index] = f"{mapping[current_index]} {line}".strip()
            ordered_pairs[-1] = (ordered_pairs[-1][0], mapping[current_index])
        else:
            raise ValueError(
                "Translation response did not retain numbering in line: " + line
            )

    expected_list = list(expected_indices)
    expected_set = set(expected_list)
    if set(mapping) != expected_set:
        mapped_keys = [index for index, _ in ordered_pairs]
        if (
            len(mapped_keys) == len(expected_list)
            and mapped_keys == list(range(1, len(mapped_keys) + 1))
        ):
            return {
                expected_list[pos]: ordered_pairs[pos][1]
                for pos in range(len(expected_list))
            }
        missing = sorted(expected_set - set(mapping))
        extra = sorted(set(mapping) - expected_set)
        details = []
        if missing:
            details.append(f"missing indices {missing}")
        if extra:
            details.append(f"unexpected indices {extra}")
        raise ValueError("Translation response mismatch: " + ", ".join(details))

    return mapping


def _fallback_sequential_mapping(
    translated: str, expected_indices: Sequence[int]
) -> Optional[Dict[int, str]]:
    xml_mapping = _parse_xml_lines(translated)
    if xml_mapping is not None:
        return xml_mapping
    lines = [line.strip() for line in translated.splitlines() if line.strip()]
    if len(lines) != len(expected_indices):
        return None

    cleaned: List[str] = []
    for line in lines:
        match = _LINE_PATTERN.match(line)
        if match:
            cleaned.append(match.group("text").strip())
        else:
            cleaned.append(line)

    if not all(cleaned):
        return None

    return {index: cleaned[pos] for pos, index in enumerate(expected_indices)}


def _parse_xml_lines(translated: str) -> Optional[Dict[int, str]]:
    stripped = translated.strip()
    if not stripped or "<" not in stripped or ">" not in stripped:
        return None
    try:
        root = ET.fromstring(stripped)
    except ET.ParseError:
        return None

    mapping: Dict[int, str] = {}
    for elem in root.findall(".//line"):
        idx_text = elem.get("index") or elem.get("id")
        if not idx_text:
            continue
        try:
            idx = int(idx_text)
        except ValueError:
            continue
        text = (elem.text or "").strip()
        mapping[idx] = text

    if not mapping:
        return None
    return mapping


def _wrap_translated_text(text: str, config: SubtitleConfig) -> List[str]:
    from . import subtitles as _subtitles  # Local import to avoid cycles

    stripped_lines = [line.strip() for line in text.splitlines() if line.strip()]
    if (
        stripped_lines
        and len(stripped_lines) <= config.max_lines
        and all(len(line) <= config.max_cpl for line in stripped_lines)
    ):
        return stripped_lines

    return _subtitles._wrap_two_lines_naive(  # type: ignore[attr-defined]
        text,
        config.max_cpl,
        config.max_lines,
        config.line_split_delimiters,
    )


def _chunks(entries: Sequence[SubtitleEntry], size: int) -> Iterator[Sequence[SubtitleEntry]]:
    for start in range(0, len(entries), size):
        yield entries[start : start + size]


def _filter_block_by_indices(
    block: Optional[str], indices: Sequence[int]
) -> Optional[str]:
    if not block:
        return None
    allowed = set(indices)
    filtered: List[str] = []
    stripped = block.strip()
    if stripped.startswith("<"):
        try:
            root = ET.fromstring(stripped)
        except ET.ParseError:
            return block
        new_root = ET.Element("subtitles")
        for elem in root.findall(".//line"):
            idx_text = elem.get("index") or elem.get("id")
            if not idx_text:
                continue
            try:
                idx = int(idx_text)
            except ValueError:
                continue
            if idx in allowed:
                new_elem = ET.SubElement(new_root, "line", index=str(idx))
                new_elem.text = (elem.text or "").strip()
        if not list(new_root):
            return None
        return ET.tostring(new_root, encoding="unicode")

    for raw_line in stripped.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _LINE_PATTERN.match(line)
        if match and int(match.group("index")) in allowed:
            filtered.append(line)
    if not filtered:
        return None
    return "\n".join(filtered)


def _invoke_translation(
    completions_api,
    *,
    target_language: str,
    numbered_block: str,
    model: str,
    first_index: int,
    last_index: int,
    expected_count: int,
    attempt: int = 0,
    retry_reason: Optional[str] = None,
    stage: str = "draft",
    draft_block: Optional[str] = None,
    review_notes: Optional[str] = None,
    full_context: Optional[str] = None,
    stats: Optional[TranslationStats] = None,
) -> str:
    reminder = ""
    if attempt > 0:
        if retry_reason == "count_mismatch":
            reason = "the number of returned lines did not match the input"
        elif retry_reason == "numbering_mismatch":
            reason = "some line numbers did not align with the input"
        elif retry_reason == "missing_text":
            reason = "one or more lines were empty"
        else:
            reason = "the required format was not respected"
        reminder = (
            f"\n\nReminder: You must output exactly {expected_count} lines."
            " Each line must start with the original number."
            f" The previous attempt failed because {reason}."
        )

    stage_notes = ""
    if stage == "refine":
        stage_notes = (
            "\n\nYou are refining an existing translation. Apply the review notes to fix issues"
            " while preserving lines that already sound natural. Ensure the final XML obeys the"
            " <subtitles><line index=\"...\">...</line></subtitles> structure."
        )

    prompt = (
        f"Translate the numbered subtitle lines into {target_language}.\n"
        "Constraints:\n"
        "- Keep the exact numbering from input; do not renumber or insert new numbers.\n"
        "- Output must be valid XML in the following form: <subtitles><line index=\"N\">text</line>...</subtitles>.\n"
        "- Provide exactly one <line> element per input line.\n"
        "- Keep it concise, idiomatic, and speakable; preserve tone, register, slang, and intensity.\n"
        "- Do not add commentary, explanations, or metadata.\n\n"
        "Example output:\n"
        "<subtitles>\n  <line index=\"123\">Texto</line>\n  <line index=\"124\">Mais texto</line>\n</subtitles>\n\n"
        f"Context: First input number = {first_index}; last input number = {last_index}.\n"
        "Treat this batch as a contiguous excerpt; keep voice/register consistent across lines."
        f"\nThe very first output line must start with '{first_index} '."
        f" The final output line must start with '{last_index} '. Do NOT restart numbering at 1 or"
        " omit any line numbers."
        f"{stage_notes}\n\n"
        "Input numbered lines:\n"
        f"{numbered_block}" + reminder
    )

    if draft_block:
        prompt += "\n\nExisting translation:\n" + draft_block
    if review_notes:
        prompt += "\n\nReview notes to address:\n" + review_notes
    if full_context:
        prompt += (
            "\n\nFull transcript context (do not renumber; for reference only):\n"
            f"{full_context}"
        )

    response = completions_api.create(
        model=model,
        temperature=0.0,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a senior audiovisual (AVT) subtitle localizer. Produce fluent,"
                    " idiomatic, speakable dialogue in the requested target language, preserving"
                    " tone, register, sarcasm, humor, and intensity (including slang/profanity)."
                    " Prefer natural phrasing over literal calques. Keep character voice"
                    " consistent within this batch. Preserve proper names, brands, acronyms,"
                    " and in-universe terms (transliterate only if widely conventional). Keep"
                    " numbers/units; adapt punctuation to target-language norms. Be concise and"
                    " oral: favor contractions and colloquial syntax where natural; avoid"
                    " bookish phrasing. Output policy (strict): one line per input line, exactly"
                    " '<number> <translated text>'. Keep the exact input numbering; do not"
                    " renumber, insert, merge, or reorder lines. No extra lines or code fences."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )

    if stats is not None:
        stats.record(stage, getattr(response, "usage", None))

    try:
        return response.choices[0].message.content  # type: ignore[index]
    except (AttributeError, IndexError) as exc:  # pragma: no cover
        raise ValueError("Unexpected LLM response format") from exc


def _translate_chunk(
    chunk: Sequence[SubtitleEntry],
    *,
    completions_api,
    target_language: str,
    config: SubtitleConfig,
    model: str,
    attempt: int = 0,
    retry_reason: Optional[str] = None,
    stage: str = "draft",
    draft_block: Optional[str] = None,
    review_notes: Optional[str] = None,
    full_context: Optional[str] = None,
    stats: Optional[TranslationStats] = None,
) -> List[SubtitleEntry]:
    numbered_block = _format_entries(chunk)
    if not numbered_block:
        return list(chunk)

    expected_indices = [entry.index for entry in chunk]
    attempt_count = attempt
    reason = retry_reason

    while True:
        LOGGER.debug(
            "Translation %s pass requesting lines %d-%d (attempt %d)",
            stage,
            expected_indices[0],
            expected_indices[-1],
            attempt_count + 1,
        )

        translated_text = _invoke_translation(
            completions_api,
            target_language=target_language,
            numbered_block=numbered_block,
            model=model,
            first_index=chunk[0].index,
            last_index=chunk[-1].index,
            expected_count=len(expected_indices),
            attempt=attempt_count,
            retry_reason=reason,
            stage=stage,
            draft_block=_filter_block_by_indices(draft_block, expected_indices),
            review_notes=review_notes,
            full_context=full_context,
            stats=stats,
        )

        mapping: Optional[Dict[int, str]]
        try:
            mapping = _parse_translated_lines(
                translated_text or "", expected_indices
            )
        except ValueError as exc:
            LOGGER.warning(
                "Translation %s pass numbering mismatch for lines %d-%d: %s",
                stage,
                expected_indices[0],
                expected_indices[-1],
                exc,
            )
            mapping = _fallback_sequential_mapping(
                translated_text or "", expected_indices
            )
            if mapping is None:
                reason = "numbering_mismatch"
                preview = "\n".join((translated_text or "").splitlines()[:3])
                if preview:
                    LOGGER.warning(
                        "Translation %s pass received misnumbered output for lines %d-%d; preview:\n%s",
                        stage,
                        expected_indices[0],
                        expected_indices[-1],
                        preview,
                    )
            else:
                LOGGER.info(
                    "Translation %s pass using sequential mapping for lines %d-%d",
                    stage,
                    expected_indices[0],
                    expected_indices[-1],
                )
        else:
            reason = None

            if mapping is not None:
                missing_indices = [idx for idx in expected_indices if idx not in mapping]
                if missing_indices:
                    reason = "numbering_mismatch"
                    mapping = None
                elif any(not (value and value.strip()) for value in mapping.values()):
                    reason = "missing_text"
                    preview = "\n".join((translated_text or "").splitlines()[:3])
                    if preview:
                        LOGGER.warning(
                            "Translation %s pass produced empty text for lines %d-%d; preview:\n%s",
                            stage,
                            expected_indices[0],
                            expected_indices[-1],
                            preview,
                        )
                    mapping = None

        if mapping is not None:
            translated: List[SubtitleEntry] = []
            for entry in chunk:
                translated_line = mapping[entry.index]
                lines = _wrap_translated_text(translated_line, config)
                translated.append(
                    SubtitleEntry(
                        index=entry.index,
                        start_ms=entry.start_ms,
                        end_ms=entry.end_ms,
                        lines=lines,
                    )
                )
            return translated

        if attempt_count < MAX_TRANSLATION_RETRIES:
            LOGGER.info(
                "Translation %s pass retrying lines %d-%d (%d/%d retries) due to %s",
                stage,
                expected_indices[0],
                expected_indices[-1],
                attempt_count + 1,
                MAX_TRANSLATION_RETRIES,
                reason or "format mismatch",
            )
            attempt_count += 1
            continue

        if len(chunk) > 1:
            LOGGER.info(
                "Translation %s pass splitting lines %d-%d after retries due to %s",
                stage,
                expected_indices[0],
                expected_indices[-1],
                reason or "format mismatch",
            )
            mid = max(1, len(chunk) // 2)
            left = _translate_chunk(
                chunk[:mid],
                completions_api=completions_api,
                target_language=target_language,
                config=config,
                model=model,
                attempt=0,
                retry_reason=None,
                stage=stage,
                draft_block=draft_block,
                review_notes=review_notes,
                full_context=full_context,
                stats=stats,
            )
            right = _translate_chunk(
                chunk[mid:],
                completions_api=completions_api,
                target_language=target_language,
                config=config,
                model=model,
                attempt=0,
                retry_reason=None,
                stage=stage,
                draft_block=draft_block,
                review_notes=review_notes,
                full_context=full_context,
                stats=stats,
            )
            return left + right

        stripped = (translated_text or "").strip()
        if not stripped:
            raise ValueError("Empty translation response")
        LOGGER.warning(
            "Translation %s pass fell back to single-line result for line %d",
            stage,
            chunk[0].index,
        )
        return [
            SubtitleEntry(
                index=chunk[0].index,
                start_ms=chunk[0].start_ms,
                end_ms=chunk[0].end_ms,
                lines=_wrap_translated_text(stripped, config),
            )
        ]


def _invoke_review(
    completions_api,
    *,
    target_language: str,
    source_block: str,
    draft_block: str,
    model: str,
    first_index: int,
    last_index: int,
    full_context: Optional[str] = None,
    stats: Optional[TranslationStats] = None,
) -> str:
    system_prompt = (
        "You are a senior subtitle editor auditing a translation for quality."
        " Flag literal calques, incorrect slang, register issues, tone mismatches,"
        " and inconsistent second-person usage. Identify misinterpreted cultural or clothing"
        " terms and missing intensity."
    )

    user_content = (
        f"Review the translation into {target_language} and report problems.\n"
        "Provide two sections strictly in this order:\n"
        "ISSUES:\n"
        "- Bullet list of notable problems (e.g., literal calque, wrong slang, clinical word,"
        " wrong intensity, inconsistent address).\n"
        "SUGGESTED FIXES:\n"
        "- Bullet list with '<line number> → concise correction or guidance'.\n"
        "Keep it concise but specific.\n\n"
        f"Source segment (lines {first_index}-{last_index}):\n{source_block}\n\n"
        "Draft translation:\n"
        f"{draft_block}\n"
    )

    if full_context:
        user_content += (
            "\nFull transcript context (reference only):\n"
            f"{full_context}\n"
        )

    response = completions_api.create(
        model=model,
        temperature=0.0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )

    if stats is not None:
        stats.record("review", getattr(response, "usage", None))

    try:
        return response.choices[0].message.content or ""
    except (AttributeError, IndexError) as exc:  # pragma: no cover
        raise ValueError("Unexpected review response format") from exc


def _prepare_client(
    model: Optional[str],
    base_url: Optional[str],
    api_key: Optional[str],
    client: Optional[object],
) -> Tuple[object, str, object]:
    resolved_model = (
        model
        or os.environ.get(LLM_MODEL_ENV)
        or os.environ.get(DEFAULT_MODEL_ENV)
    )
    resolved_base_url = base_url or os.environ.get(LLM_BASE_URL_ENV)
    resolved_api_key = api_key or require_api_key(env_var=LLM_API_KEY_ENV)

    if client is None:
        try:
            from openai import OpenAI
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise SystemExit(
                "Missing dependency: openai\nInstall it with 'pip install openai' and retry."
            ) from exc

        client_kwargs = {"api_key": resolved_api_key}
        if resolved_base_url:
            client_kwargs["base_url"] = resolved_base_url
        client = OpenAI(**client_kwargs)

    chat_completions = getattr(client, "chat", None)
    if chat_completions is None or not hasattr(chat_completions, "completions"):
        raise TypeError("Client does not expose chat.completions API")

    completions_api = chat_completions.completions
    if not hasattr(completions_api, "create"):
        raise TypeError("chat.completions object must provide a create() method")

    return completions_api, resolved_model, client


def translate_entries(
    entries: Sequence[SubtitleEntry],
    *,
    target_language: str,
    config: SubtitleConfig,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    client: Optional[object] = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    stats: Optional[TranslationStats] = None,
) -> List[SubtitleEntry]:
    """Translate subtitle entries to a target language while preserving timings."""

    if not entries:
        return []

    if chunk_size <= 0:
        chunk_size = len(entries)
    else:
        chunk_size = max(1, int(chunk_size))

    completions_api, resolved_model, _ = _prepare_client(
        model,
        base_url,
        api_key,
        client,
    )

    stats = stats or TranslationStats()
    full_context = _format_entries_xml(entries)
    translated_entries: List[SubtitleEntry] = []

    for chunk in _chunks(entries, chunk_size):
        translated_entries.extend(
            _translate_chunk(
                chunk,
                completions_api=completions_api,
                target_language=target_language,
                config=config,
                model=resolved_model,
                full_context=full_context,
                stats=stats,
            )
        )

    return translated_entries


def translate_entries_with_review(
    entries: Sequence[SubtitleEntry],
    *,
    target_language: str,
    config: SubtitleConfig,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    client: Optional[object] = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    stats: Optional[TranslationStats] = None,
) -> List[SubtitleEntry]:
    """Translate with a draft-review-refine workflow to improve quality."""

    if not entries:
        return []

    if chunk_size <= 0:
        chunk_size = len(entries)
    else:
        chunk_size = max(1, int(chunk_size))

    completions_api, resolved_model, _ = _prepare_client(
        model,
        base_url,
        api_key,
        client,
    )

    stats = stats or TranslationStats()
    full_context_plain = _format_entries(entries)
    full_context_xml = _format_entries_xml(entries)

    draft_entries: List[SubtitleEntry] = []
    for chunk in _chunks(entries, chunk_size):
        draft_entries.extend(
            _translate_chunk(
                chunk,
                completions_api=completions_api,
                target_language=target_language,
                config=config,
                model=resolved_model,
                stage="draft",
                full_context=full_context_xml,
                stats=stats,
            )
        )
    draft_block_plain = _format_entries(draft_entries)
    draft_block_xml = _format_entries_xml(draft_entries)
    first_index = entries[0].index
    last_index = entries[-1].index

    review_notes = _invoke_review(
        completions_api,
        target_language=target_language,
        source_block=full_context_plain,
        draft_block=draft_block_plain,
        model=resolved_model,
        first_index=first_index,
        last_index=last_index,
        full_context=full_context_xml,
        stats=stats,
    )

    LOGGER.info(
        "Translation review received %d characters for lines %d-%d",
        len(review_notes),
        first_index,
        last_index,
    )

    refined_entries: List[SubtitleEntry] = []
    for chunk in _chunks(entries, chunk_size):
        refined_entries.extend(
            _translate_chunk(
                chunk,
                completions_api=completions_api,
                target_language=target_language,
                config=config,
                model=resolved_model,
                stage="refine",
                draft_block=draft_block_xml,
                review_notes=review_notes,
                full_context=full_context_xml,
                stats=stats,
            )
        )

    return refined_entries


__all__ = [
    "LLM_API_KEY_ENV",
    "LLM_BASE_URL_ENV",
    "LLM_MODEL_ENV",
    "translate_entries",
    "translate_entries_with_review",
    "TranslationStats",
]
