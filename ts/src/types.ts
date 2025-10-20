export interface Token {
  text?: string;
  start_ms?: number;
  end_ms?: number;
  confidence?: number;
  speaker?: string | null;
  language?: string | null;
  is_audio_event?: boolean | null;
  [key: string]: unknown;
}

export interface Transcript {
  id?: string;
  text?: string;
  tokens?: Token[];
  [key: string]: unknown;
}

export interface SubtitleSegment {
  start: number;
  end: number;
  tokens?: Token[];
  text?: string;
  prefix_ellipsis?: boolean;
  suffix_ellipsis?: boolean;
  [key: string]: unknown;
}

export interface SubtitleEntry {
  index: number;
  start_ms: number;
  end_ms: number;
  lines: string[];
}

export interface SubtitleConfigOptions {
  gapMs?: number;
  minDurMs?: number;
  maxDurMs?: number;
  maxCps?: number;
  maxCpl?: number;
  maxLines?: number;
  splitOnSpeaker?: boolean;
  ellipses?: boolean;
}
