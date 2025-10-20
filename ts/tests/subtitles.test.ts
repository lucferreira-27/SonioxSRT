import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { describe, expect, it } from "vitest";

import {
  SubtitleConfig,
  extractTokens,
  renderSegments,
  srt,
  tokensToSubtitleSegments,
  writeSrtFile
} from "../src/subtitles";
import { Transcript } from "../src/types";

const repoRoot = path.resolve(__dirname, "..", "..");
const samplesDir = path.join(repoRoot, "samples");
const transcriptPath = path.join(samplesDir, "response.json");

const transcript: Transcript = JSON.parse(
  fs.readFileSync(transcriptPath, "utf-8")
);
const tokens = extractTokens(transcript);

describe("subtitles", () => {
  it("builds segments from tokens", () => {
    const config = new SubtitleConfig({
      maxCps: 18,
      maxDurMs: 6000,
      minDurMs: 800
    });
    const segments = tokensToSubtitleSegments(tokens, config);

    expect(segments.length).toBeGreaterThan(0);
    const starts = segments.map((segment) => segment.start);
    const ends = segments.map((segment) => segment.end);
    expect([...starts]).toEqual([...starts].sort((a, b) => a - b));
    expect(ends.every((end, idx) => end >= starts[idx])).toBe(true);
    expect(segments.every((segment) => segment.tokens && segment.tokens.length > 0)).toBe(true);
  });

  it("renders segments and writes srt", () => {
    const config = new SubtitleConfig({
      maxCps: 18,
      maxDurMs: 6000,
      maxCpl: 32
    });
    const segments = tokensToSubtitleSegments(tokens, config);
    const entries = renderSegments(segments, config);

    expect(entries.length).toBeGreaterThan(0);
    expect(entries.map((entry) => entry.index)).toEqual(
      Array.from({ length: entries.length }, (_, i) => i + 1)
    );
    expect(
      entries.every((entry) =>
        entry.lines.every((line) => line.length <= config.max_cpl)
      )
    ).toBe(true);

    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "sonioxsrt-ts-"));
    const output = path.join(tmpDir, "output.srt");
    writeSrtFile(entries, output);
    const content = fs.readFileSync(output, "utf-8").trim().split(/\r?\n/);

    expect(content[0]).toBe("1");
    expect(content[1]).toContain("-->");
    expect(content[2].length).toBeGreaterThan(0);
  });

  it("rejects transcript without tokens", () => {
    expect(() => extractTokens({ text: "hi" })).toThrowError();
  });

  it("writes srt from dict", () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "sonioxsrt-ts-"));
    const output = path.join(tmpDir, "from_dict.srt");
    const result = srt(transcript, output);

    expect(result).toBe(output);
    expect(fs.existsSync(output)).toBe(true);
    const content = fs.readFileSync(output, "utf-8");
    expect(content.startsWith("1\n")).toBe(true);
  });

  it("writes srt from file path", () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "sonioxsrt-ts-"));
    const output = path.join(tmpDir, "from_file.srt");
    srt(transcriptPath, output);
    expect(fs.existsSync(output)).toBe(true);
  });
});
