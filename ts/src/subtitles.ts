import fs from "node:fs";
import path from "node:path";
import { Token, Transcript, SubtitleEntry, SubtitleConfigOptions, SubtitleSegment } from "./types";

const SENTENCE_ENDERS = new Set(["。", "｡", ".", "．", "！", "!", "？", "?"]);
const MINOR_BREAKERS = new Set([",", "，", ";", "；", ":", "：", "、", "—", "–", "-", "･"]);

export const DEFAULT_GAP_MS = 1200;
export const DEFAULT_MIN_DUR_MS = 1000;
export const DEFAULT_MAX_DUR_MS = 7000;
export const DEFAULT_MAX_CPS = 17;

const PUNCT = new Set([".", ",", "!", "?", ";", ":", "–", "—", "-", "…", "，", "；", "：", "｡", "．", "･"]);

export class SubtitleConfig {
  gap_ms: number;
  min_dur_ms: number;
  max_dur_ms: number;
  max_cps: number;
  max_cpl: number;
  max_lines: number;
  line_split_delimiters: string[];
  segment_on_sentence: boolean;
  split_on_speaker: boolean;
  ellipses: boolean;

  constructor(options: SubtitleConfigOptions = {}) {
    this.gap_ms = options.gapMs ?? DEFAULT_GAP_MS;
    this.min_dur_ms = options.minDurMs ?? DEFAULT_MIN_DUR_MS;
    this.max_dur_ms = options.maxDurMs ?? DEFAULT_MAX_DUR_MS;
    this.max_cps = options.maxCps ?? DEFAULT_MAX_CPS;
    this.max_cpl = options.maxCpl ?? 42;
    this.max_lines = options.maxLines ?? 2;
    const delimiters = options.lineSplitDelimiters ?? [];
    const deduped = Array.from(new Set(delimiters.filter((value) => value.trim().length > 0)));
    this.line_split_delimiters = deduped;
    this.segment_on_sentence = options.segmentOnSentence ?? false;
    this.split_on_speaker = options.splitOnSpeaker ?? false;
    this.ellipses = options.ellipses ?? false;
  }
}

function containsCjk(text: string): boolean {
  for (const char of text) {
    const code = char.codePointAt(0);
    if (!code) {
      continue;
    }
    if (
      (code >= 0x3040 && code <= 0x30ff) || // Hiragana + Katakana
      (code >= 0x3400 && code <= 0x4dbf) || // CJK Extension A
      (code >= 0x4e00 && code <= 0x9fff) || // CJK Unified
      (code >= 0xf900 && code <= 0xfaff)
    ) {
      return true;
    }
  }
  return false;
}

function formatTimestamp(ms: number): string {
  const millis = Math.max(0, Math.floor(ms));
  const totalSeconds = Math.floor(millis / 1000);
  const remainderMillis = millis % 1000;
  const seconds = totalSeconds % 60;
  const totalMinutes = Math.floor(totalSeconds / 60);
  const minutes = totalMinutes % 60;
  const hours = Math.floor(totalMinutes / 60);
  return `${hours.toString().padStart(2, "0")}:${minutes
    .toString()
    .padStart(2, "0")}:${seconds.toString().padStart(2, "0")},${remainderMillis
    .toString()
    .padStart(3, "0")}`;
}

function isSentenceBreak(text?: string): boolean {
  return text ? SENTENCE_ENDERS.has(text) : false;
}

function firstNonEmpty<T>(values: Iterable<T | undefined | null>): T | undefined {
  for (const value of values) {
    if (value !== undefined && value !== null && value !== "") {
      return value;
    }
  }
  return undefined;
}

function concatText(tokens: Token[]): string {
  return tokens.map((token) => (token.text ?? "")).join("").trim();
}

interface WordToken extends Token {
  text: string;
  start_ms: number;
  end_ms: number;
  _inner?: Token[];
  _prefix_space?: boolean;
}

function tokensToWords(tokens: Token[]): WordToken[] {
  const words: WordToken[] = [];
  let currentTokens: Token[] = [];
  let currentText: string[] = [];
  let currentStart: number | undefined;
  let currentEnd: number | undefined;

  const flush = (): void => {
    if (currentTokens.length === 0) {
      return;
    }
    const prefixSpace = Boolean(
      currentTokens.length > 0 && (currentTokens[0] as WordToken)._prefix_space
    );
    const text = `${prefixSpace ? " " : ""}${currentText.join("")}`;
    words.push({
      text,
      start_ms: currentStart ?? 0,
      end_ms: currentEnd ?? currentStart ?? 0,
      _inner: [...currentTokens],
      _prefix_space: prefixSpace
    });
    currentTokens = [];
    currentText = [];
    currentStart = undefined;
    currentEnd = undefined;
  };

  for (const token of tokens) {
    const rawText = token.text ?? "";
    if (!rawText) {
      continue;
    }
    const startsSpace = rawText[0]?.trim().length === 0;
    const clean = rawText.trimStart();
    const isPunct =
      clean.length > 0 &&
      [...clean].every((char) => PUNCT.has(char));

    const tokenStart = token.start_ms;
    const tokenEnd = token.end_ms;

    const addToCurrent = (textPart: string, prefixSpace = false): void => {
      currentTokens.push(token);
      currentText.push(textPart);
      if (prefixSpace) {
        (token as WordToken)._prefix_space = true;
      }
      if (tokenStart !== undefined) {
        currentStart = currentStart === undefined ? tokenStart : Math.min(currentStart, tokenStart);
      }
      if (tokenEnd !== undefined) {
        currentEnd = currentEnd === undefined ? tokenEnd : Math.max(currentEnd, tokenEnd);
      }
    };

    if (startsSpace) {
      flush();
      addToCurrent(clean, true);
    } else {
      if (currentTokens.length > 0) {
        if (isPunct) {
          addToCurrent(clean);
        } else if (
          containsCjk(clean) &&
          containsCjk(currentText.join(""))
        ) {
          flush();
          addToCurrent(clean);
        } else {
          addToCurrent(clean);
        }
      } else {
        addToCurrent(clean);
      }
    }

    if (
      clean.length > 0 &&
      (
        SENTENCE_ENDERS.has(clean.at(-1) ?? "") ||
        MINOR_BREAKERS.has(clean.at(-1) ?? "") ||
        (containsCjk(clean) && clean.length === 1)
      )
    ) {
      flush();
    }
  }

  flush();

  if (words.length > 0 && words[0].text.startsWith(" ")) {
    words[0].text = words[0].text.trimStart();
  }

  return words;
}

function safeBoundary(prevText: string, nextText: string): boolean {
  if (!nextText) {
    return true;
  }
  if (nextText.startsWith(" ")) {
    return true;
  }
  const lastChar = prevText.slice(-1);
  return lastChar === " " || SENTENCE_ENDERS.has(lastChar) || MINOR_BREAKERS.has(lastChar);
}

export function buildSegments(
  tokens: WordToken[],
  gapThreshold: number,
  splitOnSpeaker: boolean,
  segmentOnSentence: boolean
): SubtitleSegment[] {
  const segments: SubtitleSegment[] = [];
  let current: WordToken[] = [];
  let currentStart: number | undefined;
  let lastTokenEnd: number | undefined;
  let currentSpeaker: string | null | undefined;

  const closeSegment = (sentenceBreak = false): void => {
    if (current.length === 0) {
      return;
    }

    const text = concatText(current as Token[]);
    if (!text) {
      current = [];
      currentStart = undefined;
      lastTokenEnd = undefined;
      currentSpeaker = undefined;
      return;
    }

    const start = currentStart ?? 0;
    const endCandidates = current.map(
      (token) =>
        token.end_ms ??
        token.start_ms ??
        start
    );
    const end = endCandidates.length > 0 ? Math.max(...endCandidates) : start;
    const speaker = firstNonEmpty(current.map((token) => token.speaker));

    segments.push({
      start,
      end,
      speaker: speaker ?? null,
      tokens: [...current],
      sentence_break: sentenceBreak
    });

    current = [];
    currentStart = undefined;
    lastTokenEnd = undefined;
    currentSpeaker = undefined;
  };

  for (const token of tokens) {
    const start = token.start_ms;
    const end = token.end_ms;
    const text = token.text ?? "";
    const speaker = token.speaker;

    if (
      splitOnSpeaker &&
      current.length > 0 &&
      speaker !== undefined &&
      currentSpeaker !== undefined &&
      speaker !== currentSpeaker
    ) {
      closeSegment();
    }

    if (
      current.length > 0 &&
      lastTokenEnd !== undefined &&
      start !== undefined
    ) {
      const gap = start - lastTokenEnd;
      if (gapThreshold > 0 && gap > gapThreshold) {
        const previousText = current[current.length - 1].text ?? "";
        if (safeBoundary(previousText, text)) {
          closeSegment();
        }
      }
    }

    if (current.length === 0 && start !== undefined) {
      currentStart = start;
    }
    current.push(token);

    if (end !== undefined) {
      lastTokenEnd = end;
    }
    if (currentSpeaker === undefined && speaker !== undefined) {
      currentSpeaker = speaker;
    }

    let sentenceBreak = false;
    if (text) {
      const trimmed = text.trim();
      if (trimmed) {
        if (isSentenceBreak(trimmed)) {
          sentenceBreak = true;
        } else if (segmentOnSentence && endsWithSentenceBreak(trimmed)) {
          sentenceBreak = true;
        }
      }
    }

    if (sentenceBreak) {
      closeSegment(true);
    }
  }

  closeSegment();
  return segments;
}

function segmentTime(seg: SubtitleSegment): [number, number] {
  return [seg.start, seg.end];
}

function segmentText(seg: SubtitleSegment): string {
  if (seg.tokens) {
    return concatText(seg.tokens);
  }
  return seg.text ?? "";
}

function charsForCps(text: string): number {
  return text.replace(/\s+/g, "").length;
}

function endsWithSentenceBreak(text?: string): boolean {
  if (!text) {
    return false;
  }
  const stripped = text.trim();
  if (stripped.length === 0) {
    return false;
  }
  const lastChar = stripped[stripped.length - 1];
  return SENTENCE_ENDERS.has(lastChar);
}

function splitTextByDelimiters(text: string, delimiters: string[]): string[] {
  if (!text) {
    return [];
  }
  const cleaned = text.replace(/\n/g, " ");
  const delimSet = new Set(delimiters.filter((value) => value.length > 0));
  if (delimSet.size === 0) {
    const stripped = cleaned.trim();
    return stripped ? [stripped] : [];
  }
  const pieces: string[] = [];
  let current = "";
  for (const char of cleaned) {
    current += char;
    if (delimSet.has(char)) {
      const chunk = current.trim();
      if (chunk.length > 0) {
        pieces.push(chunk);
      }
      current = "";
    }
  }
  const remainder = current.trim();
  if (remainder.length > 0) {
    pieces.push(remainder);
  }
  return pieces;
}

function partitionChunks(
  chunks: string[],
  maxLines: number,
  maxCpl: number
): string[] | null {
  if (maxLines <= 0) {
    return [];
  }
  if (chunks.length === 0) {
    return [];
  }

  const helper = (start: number, remaining: number): string[] | null => {
    if (start === chunks.length) {
      return [];
    }
    if (remaining === 0) {
      return null;
    }

    let line = "";
    for (let end = start; end < chunks.length; end += 1) {
      line = line.length > 0 ? `${line} ${chunks[end]}` : chunks[end];
      if (line.length > maxCpl) {
        break;
      }
      const rest = helper(end + 1, remaining - 1);
      if (rest !== null) {
        return [line, ...rest];
      }
    }
    return null;
  };

  return helper(0, maxLines);
}

function wrapWithPreferredDelimiters(
  text: string,
  delimiters: string[],
  maxCpl: number,
  maxLines: number
): string[] | null {
  if (maxLines <= 1) {
    return null;
  }

  const chunks = splitTextByDelimiters(text, delimiters);
  if (chunks.length <= 1) {
    return null;
  }

  const partition = partitionChunks(chunks, maxLines, maxCpl);
  if (!partition) {
    return null;
  }

  const lines = partition
    .map((line) => line.trim())
    .filter((line) => line.length > 0);

  if (lines.length <= 1) {
    return null;
  }

  return lines.slice(0, maxLines);
}

function isSafeAt(tokens: WordToken[], index: number): boolean {
  if (index <= 0 || index >= tokens.length) {
    return true;
  }
  const left = tokens[index - 1].text ?? "";
  const right = tokens[index].text ?? "";
  if (right.startsWith(" ")) {
    return true;
  }
  if (left.endsWith(" ")) {
    return true;
  }
  const lastChar = left.slice(-1);
  return SENTENCE_ENDERS.has(lastChar) || MINOR_BREAKERS.has(lastChar);
}

function adjustToSafe(tokens: WordToken[], index: number): number {
  if (isSafeAt(tokens, index)) {
    return index;
  }
  for (let j = index + 1; j < tokens.length; j += 1) {
    if (isSafeAt(tokens, j)) {
      return j;
    }
  }
  for (let j = index - 1; j > 0; j -= 1) {
    if (isSafeAt(tokens, j)) {
      return j;
    }
  }
  return index;
}

function findSplitIndex(tokens: WordToken[]): number {
  const n = tokens.length;
  if (n <= 1) {
    return 1;
  }

  const totalChars = tokens.reduce((sum, token) => sum + (token.text ?? "").length, 0);
  const midChars = Math.floor(totalChars / 2);

  const cumulative: number[] = [];
  const safeAfter: number[] = [];
  let acc = 0;

  for (let i = 0; i < tokens.length; i += 1) {
    const token = tokens[i];
    const txt = token.text ?? "";
    acc += txt.length;
    cumulative.push(acc);
    if (i < tokens.length - 1) {
      const next = tokens[i + 1].text ?? "";
      if (safeBoundary(txt, next)) {
        safeAfter.push(i + 1);
      }
    }
  }

  if (safeAfter.length > 0) {
    let bestIndex = safeAfter[0];
    let bestDelta = Math.abs(cumulative[bestIndex - 1] - midChars);
    for (const candidate of safeAfter) {
      const delta = Math.abs(cumulative[candidate - 1] - midChars);
      if (delta < bestDelta) {
        bestIndex = candidate;
        bestDelta = delta;
      }
    }
    return adjustToSafe(tokens, bestIndex);
  }

  const mid = Math.floor(n / 2);
  for (let i = mid; i > 0; i -= 1) {
    const t = tokens[i - 1].text ?? "";
    if (t && SENTENCE_ENDERS.has(t.slice(-1))) {
      return adjustToSafe(tokens, i);
    }
  }
  for (let i = mid + 1; i < n; i += 1) {
    const t = tokens[i - 1].text ?? "";
    if (t && SENTENCE_ENDERS.has(t.slice(-1))) {
      return adjustToSafe(tokens, i);
    }
  }

  return adjustToSafe(tokens, mid);
}

export function enforceReadability(
  segments: SubtitleSegment[],
  config: SubtitleConfig
): SubtitleSegment[] {
  const out: SubtitleSegment[] = [];
  const maxChars = config.max_cpl * config.max_lines;
  const preserveSentenceBreaks = config.segment_on_sentence;

  for (const segment of segments) {
    const queue: SubtitleSegment[] = [segment];
    while (queue.length > 0) {
      const current = queue.shift()!;
      const text = segmentText(current);
      const [start, end] = segmentTime(current);
      const duration = Math.max(1, end - start);
      const cps = charsForCps(text) / (duration / 1000);

      const tokens = (current.tokens ?? []) as WordToken[];
      if (
        (duration > config.max_dur_ms || cps > config.max_cps || text.length > maxChars) &&
        tokens.length > 1
      ) {
        const idx = findSplitIndex(tokens);
        const leftTokens = tokens.slice(0, idx);
        const rightTokens = tokens.slice(idx);

        const left: SubtitleSegment = {
          tokens: leftTokens,
          start: leftTokens[0].start_ms ?? start,
          end: leftTokens[leftTokens.length - 1].end_ms ?? end,
          speaker: current.speaker ?? null,
          sentence_break: false
        };
        const right: SubtitleSegment = {
          tokens: rightTokens,
          start: rightTokens[0].start_ms ?? start,
          end: rightTokens[rightTokens.length - 1].end_ms ?? end,
          speaker: current.speaker ?? null,
          sentence_break: Boolean(current.sentence_break)
        };
        if (config.ellipses) {
          left.suffix_ellipsis = true;
          right.prefix_ellipsis = true;
        }
        queue.unshift(right);
        queue.unshift(left);
      } else {
        out.push(current);
      }
    }
  }

  let changed = true;
  let currentSegments = out;
  while (changed) {
    changed = false;
    const merged: SubtitleSegment[] = [];
    let i = 0;
    while (i < currentSegments.length) {
      const segment = currentSegments[i];
      const [start, end] = segmentTime(segment);
      const duration = end - start;
      if (duration < config.min_dur_ms && i + 1 < currentSegments.length) {
        if (preserveSentenceBreaks && segment.sentence_break) {
          merged.push(segment);
          i += 1;
          continue;
        }
        const next = currentSegments[i + 1];
        const [nStart, nEnd] = segmentTime(next);
        if (nEnd - start <= config.max_dur_ms) {
          const mergedTokens = [
            ...(segment.tokens ?? []),
            ...(next.tokens ?? [])
          ] as WordToken[];
          merged.push({
            tokens: mergedTokens,
            start,
            end: nEnd,
            speaker: segment.speaker ?? next.speaker ?? null,
            sentence_break: Boolean(next.sentence_break)
          });
          i += 2;
          changed = true;
          continue;
        }
      }
      merged.push(segment);
      i += 1;
    }
    currentSegments = merged;
  }

  return currentSegments;
}

function wrapTwoLinesNaive(
  text: string,
  maxCpl: number,
  maxLines: number,
  preferredDelimiters: string[]
): string[] {
  const trimmed = text.trim();
  if (maxLines <= 1) {
    return [trimmed];
  }

  if (preferredDelimiters.length > 0) {
    const lines = wrapWithPreferredDelimiters(
      trimmed,
      preferredDelimiters,
      maxCpl,
      maxLines
    );
    if (lines) {
      return lines;
    }
  }

  if (trimmed.length <= maxCpl) {
    return [trimmed];
  }

  if (trimmed.includes(" ")) {
    const target = Math.floor(trimmed.length / 2);
    let breakPos: number | undefined;
    for (let delta = 0; delta < trimmed.length; delta += 1) {
      const left = target - delta;
      const right = target + delta;
      if (left > 0 && trimmed[left] === " ") {
        breakPos = left;
        break;
      }
      if (right < trimmed.length && trimmed[right] === " ") {
        breakPos = right;
        break;
      }
    }
    if (breakPos === undefined) {
      breakPos = Math.min(trimmed.length, maxCpl);
    }
    let line1 = trimmed.slice(0, breakPos).trim();
    let line2 = trimmed.slice(breakPos).trim();
    if (line1.length > maxCpl) {
      line1 = line1.slice(0, maxCpl).trimEnd();
    }
    if (line2.length > maxCpl && maxLines > 1) {
      line2 = line2.slice(0, maxCpl).trimEnd();
    }
    return maxLines >= 2 ? [line1, line2] : [line1];
  }

  const line1 = trimmed.slice(0, maxCpl);
  const line2 = trimmed.slice(maxCpl, maxCpl * 2);
  if (line2) {
    return maxLines >= 2 ? [line1, line2] : [line1];
  }
  return [line1];
}

function wrapTwoLinesTokenAware(
  tokens: WordToken[],
  text: string,
  maxCpl: number,
  maxLines: number,
  preferredDelimiters: string[]
): string[] {
  const stripped = text.trim();
  if (maxLines <= 1) {
    return [stripped];
  }

  if (preferredDelimiters.length > 0) {
    const lines = wrapWithPreferredDelimiters(
      stripped,
      preferredDelimiters,
      maxCpl,
      maxLines
    );
    if (lines) {
      return lines;
    }
  }

  if (stripped.length <= maxCpl) {
    return [stripped];
  }

  const safeAfter = new Set<number>();
  for (let i = 0; i < tokens.length - 1; i += 1) {
    const current = tokens[i].text ?? "";
    const next = tokens[i + 1].text ?? "";
    if (!next) {
      continue;
    }
    if (safeBoundary(current, next)) {
      safeAfter.add(i);
    }
  }

  let charLen = 0;
  let lastSafe: number | undefined;
  for (let i = 0; i < tokens.length; i += 1) {
    charLen += (tokens[i].text ?? "").length;
    if (safeAfter.has(i)) {
      lastSafe = i;
    }
    if (charLen > maxCpl) {
      if (lastSafe !== undefined) {
        let candidate = lastSafe;
        while (candidate >= 0) {
          if (safeAfter.has(candidate)) {
            const left = concatText(tokens.slice(0, candidate + 1)).trimEnd();
            if (left.length <= maxCpl) {
              const right = concatText(tokens.slice(candidate + 1)).trimStart();
              if (right.length <= maxCpl) {
                return [left, right];
              }
            }
          }
          candidate -= 1;
        }
      }
      break;
    }
  }

  const totalChars = tokens.reduce(
    (sum, token) => sum + (token.text ?? "").length,
    0
  );
  const target = Math.floor(totalChars / 2);
  let acc = 0;
  let nearest: number | undefined;
  let bestDelta = Number.POSITIVE_INFINITY;
  for (let i = 0; i < tokens.length - 1; i += 1) {
    acc += (tokens[i].text ?? "").length;
    if (safeAfter.has(i)) {
      const delta = Math.abs(acc - target);
      if (delta < bestDelta) {
        nearest = i;
        bestDelta = delta;
      }
    }
  }
  if (nearest !== undefined) {
    const left = concatText(tokens.slice(0, nearest + 1)).trimEnd();
    const right = concatText(tokens.slice(nearest + 1)).trimStart();
    if (left.length <= maxCpl && right.length <= maxCpl) {
      return [left, right];
    }
  }

  return [stripped];
}

export function extractTokens(transcript: Transcript): Token[] {
  if (Array.isArray(transcript.tokens) && transcript.tokens.length > 0) {
    return transcript.tokens as Token[];
  }

  const nested = collectTokens(transcript, true);
  if (nested.length > 0) {
    return nested;
  }

  throw new Error("No tokens found in transcript.");
}

const NESTED_TOKEN_KEYS = [
  "alternatives",
  "segments",
  "paragraphs",
  "turns",
  "entries",
  "results",
  "items"
] as const;

function collectTokens(value: unknown, skipImmediate = false): Token[] {
  if (value === null || value === undefined) {
    return [];
  }

  const tokens: Token[] = [];

  const collectFromIterable = (items: Iterable<unknown>): void => {
    for (const item of items) {
      tokens.push(...collectTokens(item, false));
    }
  };

  if (Array.isArray(value)) {
    if (
      value.length > 0 &&
      value.every(
        (item) =>
          typeof item === "object" &&
          item !== null &&
          "text" in (item as Record<string, unknown>)
      )
    ) {
      tokens.push(...(value as Token[]));
    } else {
      collectFromIterable(value);
    }
    return tokens;
  }

  if (typeof value === "object") {
    const obj = value as Record<string, unknown>;
    if (!skipImmediate && Array.isArray(obj.tokens) && obj.tokens.length > 0) {
      tokens.push(...(obj.tokens as Token[]));
    }
    for (const key of NESTED_TOKEN_KEYS) {
      const nested = obj[key];
      if (nested !== undefined) {
        tokens.push(...collectTokens(nested, false));
      }
    }
  }

  return tokens;
}

export function tokensToSubtitleSegments(tokens: Token[], config: SubtitleConfig): SubtitleSegment[] {
  const words = tokensToWords(tokens);
  const segments = buildSegments(
    words,
    config.gap_ms,
    config.split_on_speaker,
    config.segment_on_sentence
  );
  if (segments.length === 0) {
    return [];
  }
  return enforceReadability(segments, config);
}

export function renderSegments(
  segments: SubtitleSegment[],
  config: SubtitleConfig
): SubtitleEntry[] {
  const entries: SubtitleEntry[] = [];
  segments.forEach((segment, index) => {
    let text = segmentText(segment);
    if (segment.prefix_ellipsis) {
      text = `…${text}`;
    }
    if (segment.suffix_ellipsis) {
      text = `${text}…`;
    }
    let lines: string[];
    const tokens = segment.tokens as WordToken[] | undefined;
    if (tokens && tokens.length > 0) {
      lines = wrapTwoLinesTokenAware(
        tokens,
        text,
        config.max_cpl,
        config.max_lines,
        config.line_split_delimiters
      );
    } else {
      lines = wrapTwoLinesNaive(
        text,
        config.max_cpl,
        config.max_lines,
        config.line_split_delimiters
      );
    }

    entries.push({
      index: index + 1,
      start_ms: segment.start,
      end_ms: segment.end,
      lines: lines.slice(0, config.max_lines)
    });
  });
  return entries;
}

export function writeSrtFile(entries: SubtitleEntry[], outputPath: string): void {
  const resolved = path.resolve(outputPath);
  const chunks: string[] = [];
  for (const entry of entries) {
    chunks.push(`${entry.index}`);
    chunks.push(
      `${formatTimestamp(entry.start_ms)} --> ${formatTimestamp(entry.end_ms)}`
    );
    for (const line of entry.lines) {
      chunks.push(line);
    }
    chunks.push("");
  }
  fs.writeFileSync(resolved, `${chunks.join("\n")}\n`, { encoding: "utf-8" });
}

export function srt(
  transcript: Transcript | string,
  outputPath = "subtitles.srt",
  config: SubtitleConfig = new SubtitleConfig()
): string {
  let data: Transcript;
  if (typeof transcript === "string") {
    const resolved = path.resolve(transcript);
    console.info(`Loading transcript from ${resolved}`);
    const raw = fs.readFileSync(resolved, "utf-8");
    data = JSON.parse(raw) as Transcript;
  } else {
    data = transcript;
  }

  const tokens = extractTokens(data);
  const segments = tokensToSubtitleSegments(tokens, config);
  if (segments.length === 0) {
    throw new Error("No subtitle segments produced from transcript.");
  }
  const entries = renderSegments(segments, config);
  const resolvedOutput = path.resolve(outputPath);
  console.info(`Writing ${entries.length} subtitles to ${resolvedOutput}`);
  writeSrtFile(entries, resolvedOutput);
  return resolvedOutput;
}
