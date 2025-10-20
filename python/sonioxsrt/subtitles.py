"""Subtitle generation utilities for Soniox transcripts."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple, Union

SENTENCE_ENDERS = {"。", ".", "！", "!", "？", "?"}
MINOR_BREAKERS = {",", ";", ":", "、", "—", "–", "-"}
DEFAULT_GAP_MS = 1200
DEFAULT_MIN_DUR_MS = 1000
DEFAULT_MAX_DUR_MS = 7000
DEFAULT_MAX_CPS = 17.0

PUNCT = set(".,!?;:–—-…")

LOGGER = logging.getLogger(__name__)


@dataclass
class SubtitleConfig:
    gap_ms: int = DEFAULT_GAP_MS
    min_dur_ms: int = DEFAULT_MIN_DUR_MS
    max_dur_ms: int = DEFAULT_MAX_DUR_MS
    max_cps: float = DEFAULT_MAX_CPS
    max_cpl: int = 42
    max_lines: int = 2
    line_split_delimiters: Tuple[str, ...] = ()
    segment_on_sentence: bool = False
    split_on_speaker: bool = False
    ellipses: bool = False


@dataclass
class SubtitleEntry:
    index: int
    start_ms: int
    end_ms: int
    lines: List[str]


def extract_tokens(transcript: dict) -> List[dict]:
    tokens = transcript.get("tokens")
    if not isinstance(tokens, list) or not tokens:
        raise ValueError("No tokens found in transcript.")
    return tokens


def format_timestamp(ms: int) -> str:
    ms = max(0, int(ms))
    seconds, millis = divmod(ms, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


def is_sentence_break(token_text: str) -> bool:
    return token_text in SENTENCE_ENDERS


def first_non_empty(values: Iterable[Optional[str]]) -> Optional[str]:
    for value in values:
        if value not in (None, ""):
            return str(value)
    return None


def _concat_text(ts: Sequence[dict]) -> str:
    return "".join(t.get("text", "") for t in ts).strip()


def tokens_to_words(tokens: Sequence[dict]) -> List[dict]:
    """Group subword tokens into word-like units to avoid mid-word splits."""
    words: List[dict] = []
    cur_tokens: List[dict] = []
    cur_text_parts: List[str] = []
    cur_start: Optional[int] = None
    cur_end: Optional[int] = None

    def flush() -> None:
        nonlocal cur_tokens, cur_text_parts, cur_start, cur_end
        if not cur_tokens:
            return
        prefix_space = bool(cur_tokens and cur_tokens[0].get("_prefix_space"))
        text = (" " if prefix_space else "") + "".join(cur_text_parts)
        words.append(
            {
                "text": text,
                "start_ms": cur_start if cur_start is not None else 0,
                "end_ms": cur_end if cur_end is not None else (cur_start or 0),
                "_inner": cur_tokens,
            }
        )
        cur_tokens = []
        cur_text_parts = []
        cur_start = None
        cur_end = None

    for tok in tokens:
        t = tok.get("text", "")
        if not t:
            continue
        starts_space = t[0].isspace()
        clean = t.lstrip()
        is_punct = clean and all(ch in PUNCT for ch in clean)

        t_start = tok.get("start_ms")
        t_end = tok.get("end_ms")

        def add_to_current(text_part: str) -> None:
            nonlocal cur_start, cur_end
            cur_tokens.append(tok)
            cur_text_parts.append(text_part)
            if t_start is not None:
                cur_start = t_start if cur_start is None else min(cur_start, t_start)
            if t_end is not None:
                cur_end = t_end if cur_end is None else max(cur_end, t_end)

        if starts_space:
            flush()
            add_to_current(clean)
            cur_tokens[-1]["_prefix_space"] = True
        else:
            if is_punct and cur_tokens:
                add_to_current(clean)
            else:
                if not cur_tokens:
                    add_to_current(clean)
                else:
                    add_to_current(clean)

    if cur_tokens:
        flush()

    if words and words[0]["text"].startswith(" "):
        words[0]["text"] = words[0]["text"].lstrip()

    return words


def build_segments(
    tokens: Sequence[dict],
    gap_threshold: int,
    split_on_speaker: bool,
    segment_on_sentence: bool,
) -> List[dict]:
    segments: List[dict] = []
    current: List[dict] = []
    current_start: Optional[int] = None
    last_token_end: Optional[int] = None
    current_speaker: Optional[str] = None

    def close_segment(sentence_break: bool = False) -> None:
        nonlocal current, current_start, last_token_end, current_speaker
        if not current:
            return

        text = _concat_text(current)
        if not text:
            current = []
            current_start = None
            last_token_end = None
            current_speaker = None
            return

        start = current_start if current_start is not None else 0
        end_candidates = [
            token.get("end_ms") or token.get("start_ms") or start for token in current
        ]
        end = max(end_candidates) if end_candidates else start
        speaker = first_non_empty(token.get("speaker") for token in current)

        segments.append(
            {
                "start": start,
                "end": end,
                "speaker": speaker,
                "tokens": current,
                "sentence_break": sentence_break,
            }
        )

        current = []
        current_start = None
        last_token_end = None
        current_speaker = None

    def _safe_boundary(prev_text: str, next_text: str) -> bool:
        if not next_text:
            return True
        return next_text.startswith(" ") or (
            prev_text.endswith(" ")
            or (
                prev_text
                and (
                    prev_text[-1] in SENTENCE_ENDERS
                    or prev_text[-1] in MINOR_BREAKERS
                )
            )
        )

    for token in tokens:
        start = token.get("start_ms")
        end = token.get("end_ms")
        text = token.get("text", "")
        speaker = token.get("speaker")

        if (
            split_on_speaker
            and current
            and speaker is not None
            and current_speaker is not None
            and speaker != current_speaker
        ):
            close_segment()

        if current and last_token_end is not None and start is not None:
            gap = start - last_token_end
            if gap_threshold > 0 and gap > gap_threshold:
                prev_text = current[-1].get("text", "")
                next_text = text
                if _safe_boundary(prev_text, next_text):
                    close_segment()

        if not current and start is not None:
            current_start = start

        current.append(token)
        if end is not None:
            last_token_end = end
        if current_speaker is None and speaker is not None:
            current_speaker = speaker

        sentence_break = False
        if text:
            if is_sentence_break(text):
                sentence_break = True
            elif segment_on_sentence and _ends_with_sentence_break(text):
                sentence_break = True

        if sentence_break:
            close_segment(sentence_break=True)

    close_segment()
    return segments


def _segment_time(seg: dict) -> Tuple[int, int]:
    start = seg["start"]
    end = seg["end"]
    return start, end


def _segment_text(seg: dict) -> str:
    return _concat_text(seg["tokens"]) if "tokens" in seg else seg.get("text", "")


def _chars_for_cps(text: str) -> int:
    return len(text.replace(" ", ""))


def _ends_with_sentence_break(text: str) -> bool:
    stripped = text.rstrip()
    if not stripped:
        return False
    return stripped[-1] in SENTENCE_ENDERS


def _split_text_by_delimiters(text: str, delimiters: Sequence[str]) -> List[str]:
    if not text:
        return []

    cleaned = text.replace("\n", " ")
    delim_set = {d for d in delimiters if d}
    if not delim_set:
        stripped = cleaned.strip()
        return [stripped] if stripped else []

    pieces: List[str] = []
    current_chars: List[str] = []
    for char in cleaned:
        current_chars.append(char)
        if char in delim_set:
            chunk = "".join(current_chars).strip()
            if chunk:
                pieces.append(chunk)
            current_chars = []

    remainder = "".join(current_chars).strip()
    if remainder:
        pieces.append(remainder)

    return pieces


def _partition_chunks(
    chunks: Sequence[str], max_lines: int, max_cpl: int
) -> Optional[List[str]]:
    if max_lines <= 0:
        return []
    if not chunks:
        return []

    def helper(start: int, remaining: int) -> Optional[List[str]]:
        if start == len(chunks):
            return []
        if remaining == 0:
            return None

        line = ""
        for end in range(start, len(chunks)):
            line = f"{line} {chunks[end]}".strip() if line else chunks[end]
            if len(line) > max_cpl:
                break
            rest = helper(end + 1, remaining - 1)
            if rest is not None:
                return [line, *rest]
        return None

    return helper(0, max_lines)


def _wrap_with_preferred_delimiters(
    text: str,
    delimiters: Sequence[str],
    max_cpl: int,
    max_lines: int,
) -> Optional[List[str]]:
    if max_lines <= 1:
        return None

    chunks = _split_text_by_delimiters(text, delimiters)
    if len(chunks) <= 1:
        return None

    partition = _partition_chunks(chunks, max_lines, max_cpl)
    if not partition:
        return None

    lines = [line.strip() for line in partition if line.strip()]
    if len(lines) <= 1:
        return None
    return lines[:max_lines]


def _find_split_index(tokens: Sequence[dict]) -> int:
    n = len(tokens)
    if n <= 1:
        return 1
    mid_chars = sum(len(t.get("text", "")) for t in tokens) // 2

    cum = []
    acc = 0
    safe_after = []
    for i, tok in enumerate(tokens):
        txt = tok.get("text", "")
        acc += len(txt)
        cum.append(acc)
        if i < n - 1:
            nxt = tokens[i + 1].get("text", "")
            if nxt.startswith(" ") or (
                txt
                and (
                    txt.endswith(" ")
                    or txt[-1] in SENTENCE_ENDERS
                    or txt[-1] in MINOR_BREAKERS
                )
            ):
                safe_after.append(i + 1)

    def _is_safe_at(k: int) -> bool:
        if k <= 0 or k >= n:
            return True
        left = tokens[k - 1].get("text", "")
        right = tokens[k].get("text", "")
        return right.startswith(" ") or (
            left.endswith(" ")
            or (
                left
                and (left[-1] in SENTENCE_ENDERS or left[-1] in MINOR_BREAKERS)
            )
        )

    def _adjust_to_safe(k: int) -> int:
        if _is_safe_at(k):
            return k
        for j in range(k + 1, n):
            if _is_safe_at(j):
                return j
        for j in range(k - 1, 0, -1):
            if _is_safe_at(j):
                return j
        return k

    if safe_after:
        best = min(safe_after, key=lambda k: abs(cum[k - 1] - mid_chars))
        return _adjust_to_safe(best)

    mid_tok = n // 2
    for i in range(mid_tok, 0, -1):
        t = tokens[i - 1].get("text", "")
        if t and t[-1] in SENTENCE_ENDERS:
            return _adjust_to_safe(i)
    for i in range(mid_tok + 1, n):
        t = tokens[i - 1].get("text", "")
        if t and t[-1] in SENTENCE_ENDERS:
            return _adjust_to_safe(i)

    return _adjust_to_safe(mid_tok)


def enforce_readability(
    segments: Sequence[dict],
    *,
    max_cps: float,
    min_dur: int,
    max_dur: int,
    max_chars: Optional[int],
    use_ellipses: bool,
    preserve_sentence_breaks: bool,
) -> List[dict]:
    out: List[dict] = []

    for seg in segments:
        queue = [seg]
        while queue:
            current = queue.pop(0)
            text = _segment_text(current)
            start, end = _segment_time(current)
            dur = max(1, end - start)
            cps = _chars_for_cps(text) / (dur / 1000.0)

            if dur > max_dur or cps > max_cps or (
                max_chars is not None and len(text) > max_chars
            ):
                toks = current["tokens"]
                if len(toks) <= 1:
                    out.append(current)
                    continue
                idx = _find_split_index(toks)
                left = {
                    "tokens": toks[:idx],
                    "start": toks[0].get("start_ms", start),
                    "end": toks[idx - 1].get("end_ms", end),
                    "sentence_break": False,
                }
                right = {
                    "tokens": toks[idx:],
                    "start": toks[idx].get("start_ms", start),
                    "end": toks[-1].get("end_ms", end),
                    "sentence_break": current.get("sentence_break", False),
                }
                if use_ellipses:
                    left["suffix_ellipsis"] = True
                    right["prefix_ellipsis"] = True
                queue.insert(0, right)
                queue.insert(0, left)
            else:
                out.append(current)

    changed = True
    current_segments = out
    while changed:
        changed = False
        merged: List[dict] = []
        i = 0
        while i < len(current_segments):
            seg = current_segments[i]
            start, end = _segment_time(seg)
            dur = end - start
            if dur < min_dur and i + 1 < len(current_segments):
                if preserve_sentence_breaks and seg.get("sentence_break"):
                    merged.append(seg)
                    i += 1
                    continue
                nxt = current_segments[i + 1]
                n_start, n_end = _segment_time(nxt)
                if n_end - start <= max_dur:
                    toks = seg["tokens"] + nxt["tokens"]
                    merged_seg = {"tokens": toks, "start": start, "end": n_end}
                    merged_seg["sentence_break"] = nxt.get("sentence_break", False)
                    merged.append(merged_seg)
                    i += 2
                    changed = True
                    continue
            merged.append(seg)
            i += 1
        current_segments = merged

    return current_segments


def _wrap_two_lines_naive(
    text: str,
    max_cpl: int,
    max_lines: int,
    preferred_delimiters: Optional[Sequence[str]] = None,
) -> List[str]:
    txt = text.strip()
    if max_lines <= 1:
        return [txt]

    preferred = tuple(preferred_delimiters or ())
    if preferred:
        lines = _wrap_with_preferred_delimiters(txt, preferred, max_cpl, max_lines)
        if lines:
            return lines

    if len(txt) <= max_cpl:
        return [txt]

    if " " in txt:
        target = len(txt) // 2
        break_pos = None
        for delta in range(0, len(txt)):
            left = target - delta
            right = target + delta
            if left > 0 and txt[left] == " ":
                break_pos = left
                break
            if right < len(txt) and txt[right] == " ":
                break_pos = right
                break
        if break_pos is None:
            break_pos = min(len(txt), max_cpl)
        line1 = txt[:break_pos].strip()
        line2 = txt[break_pos:].strip()
        if len(line1) > max_cpl:
            line1 = line1[:max_cpl].rstrip()
        if len(line2) > max_cpl and max_lines > 1:
            line2 = line2[:max_cpl].rstrip()
        return [line1, line2] if max_lines >= 2 else [line1]

    line1 = txt[:max_cpl]
    line2 = txt[max_cpl : max_cpl * 2]
    return [line1, line2] if line2 and max_lines >= 2 else [line1]


def _wrap_two_lines_token_aware(
    tokens: Sequence[dict],
    text: str,
    max_cpl: int,
    max_lines: int,
    preferred_delimiters: Optional[Sequence[str]] = None,
) -> List[str]:
    stripped = text.strip()
    if max_lines <= 1:
        return [stripped]

    preferred = tuple(preferred_delimiters or ())
    if preferred:
        lines = _wrap_with_preferred_delimiters(stripped, preferred, max_cpl, max_lines)
        if lines:
            return lines

    if len(stripped) <= max_cpl:
        return [stripped]

    safe_after = set()
    for i in range(len(tokens) - 1):
        cur = tokens[i].get("text", "")
        nxt = tokens[i + 1].get("text", "")
        if not nxt:
            continue
        if nxt.startswith(" ") or (
            cur
            and (
                cur.endswith(" ")
                or cur[-1] in SENTENCE_ENDERS
                or cur[-1] in MINOR_BREAKERS
            )
        ):
            safe_after.add(i)

    char_len = 0
    last_safe = None
    for i, tok in enumerate(tokens):
        char_len += len(tok.get("text", ""))
        if i in safe_after:
            last_safe = i
        if char_len > max_cpl:
            if last_safe is not None:
                candidate = last_safe
                while candidate >= 0:
                    if candidate in safe_after:
                        left_text = _concat_text(tokens[: candidate + 1]).rstrip()
                        if len(left_text) <= max_cpl:
                            right_text = _concat_text(tokens[candidate + 1 :]).lstrip()
                            if len(right_text) <= max_cpl:
                                return [left_text, right_text]
                    candidate -= 1
            break

    total_chars = sum(len(t.get("text", "")) for t in tokens)
    target = total_chars // 2
    acc = 0
    nearest = None
    best_delta = 10**9
    for i in range(len(tokens) - 1):
        acc += len(tokens[i].get("text", ""))
        if i in safe_after:
            delta = abs(acc - target)
            if delta < best_delta:
                best_delta = delta
                nearest = i
    if nearest is not None:
        left_text = _concat_text(tokens[: nearest + 1]).rstrip()
        right_text = _concat_text(tokens[nearest + 1 :]).lstrip()
        if len(left_text) <= max_cpl and len(right_text) <= max_cpl:
            return [left_text, right_text]

    return [stripped]


def tokens_to_subtitle_segments(
    tokens: Sequence[dict],
    config: SubtitleConfig,
) -> List[dict]:
    words = tokens_to_words(tokens)
    segments = build_segments(
        words,
        config.gap_ms,
        config.split_on_speaker,
        config.segment_on_sentence,
    )
    if not segments:
        return []
    segments = enforce_readability(
        segments,
        max_cps=config.max_cps,
        min_dur=config.min_dur_ms,
        max_dur=config.max_dur_ms,
        max_chars=config.max_cpl * config.max_lines,
        use_ellipses=config.ellipses,
        preserve_sentence_breaks=config.segment_on_sentence,
    )
    return segments


def render_segments(
    segments: Sequence[dict],
    config: SubtitleConfig,
) -> List[SubtitleEntry]:
    entries: List[SubtitleEntry] = []
    for idx, seg in enumerate(segments, start=1):
        text = _segment_text(seg)
        if seg.get("prefix_ellipsis"):
            text = "…" + text
        if seg.get("suffix_ellipsis"):
            text = text + "…"

        tokens = seg.get("tokens")
        if tokens:
            lines = _wrap_two_lines_token_aware(
                tokens,
                text,
                config.max_cpl,
                config.max_lines,
                config.line_split_delimiters,
            )
        else:
            lines = _wrap_two_lines_naive(
                text,
                config.max_cpl,
                config.max_lines,
                config.line_split_delimiters,
            )
        entries.append(
            SubtitleEntry(
                index=idx,
                start_ms=seg["start"],
                end_ms=seg["end"],
                lines=lines[: config.max_lines],
            )
        )
    return entries


def write_srt_file(entries: Sequence[SubtitleEntry], output_path: Path | str) -> None:
    path = Path(output_path)
    with path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(f"{entry.index}\n")
            handle.write(
                f"{format_timestamp(entry.start_ms)} --> {format_timestamp(entry.end_ms)}\n"
            )
            for line in entry.lines:
                handle.write(f"{line}\n")
            handle.write("\n")


def srt(
    transcript: Union[dict, Path, str],
    output_path: Path | str = "subtitles.srt",
    config: Optional[SubtitleConfig] = None,
) -> Path:
    """Create an SRT file from a transcript dict or JSON file."""
    if config is None:
        config = SubtitleConfig()

    if isinstance(transcript, (str, Path)):
        path = Path(transcript)
        LOGGER.info("Loading transcript from %s", path)
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = transcript

    tokens = extract_tokens(data)
    segments = tokens_to_subtitle_segments(tokens, config)
    if not segments:
        raise ValueError("No subtitle segments produced from transcript.")

    entries = render_segments(segments, config)
    output_path = Path(output_path)
    LOGGER.info("Writing %d subtitles to %s", len(entries), output_path)
    write_srt_file(entries, output_path)
    return output_path


__all__ = [
    "SubtitleConfig",
    "SubtitleEntry",
    "extract_tokens",
    "render_segments",
    "srt",
    "tokens_to_subtitle_segments",
    "write_srt_file",
]
