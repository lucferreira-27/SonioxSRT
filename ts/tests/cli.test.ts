import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import toSrtMain from "../src/cli/to_srt";
import transcribeMain from "../src/cli/transcribe";
import * as transcriberModule from "../src/transcriber";

const repoRoot = path.resolve(__dirname, "..", "..");
const samplesDir = path.join(repoRoot, "samples");
const transcriptPath = path.join(samplesDir, "response.json");

afterEach(() => {
  vi.restoreAllMocks();
});

describe("CLI", () => {
  it("converts JSON to SRT", async () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "sonioxsrt-ts-"));
    const output = path.join(tmpDir, "subtitles.srt");
    const exitCode = await toSrtMain([
      "node",
      "to_srt",
      "--input",
      transcriptPath,
      "--output",
      output,
      "--max-cpl",
      "32"
    ]);

    expect(exitCode).toBe(0);
    expect(fs.existsSync(output)).toBe(true);
    const content = fs.readFileSync(output, "utf-8").trim().split(/\r?\n/);
    expect(content[0]).toBe("1");
  });

  it("fails when audio file missing", async () => {
    const missing = path.join(os.tmpdir(), "missing.wav");
    const exitCode = await transcribeMain([
      "node",
      "transcribe",
      "--audio",
      missing
    ]);
    expect(exitCode).toBe(1);
  });

  it("invokes transcribe helper", async () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "sonioxsrt-ts-"));
    const audioPath = path.join(tmpDir, "audio.wav");
    const output = path.join(tmpDir, "response.json");
    fs.writeFileSync(audioPath, "RIFF");

    const spy = vi
      .spyOn(transcriberModule, "transcribeToFile")
      .mockResolvedValue({ id: "ok" } as any);

    const exitCode = await transcribeMain([
      "node",
      "transcribe",
      "--audio",
      audioPath,
      "--output",
      output,
      "--model",
      "demo-model"
    ]);

    expect(exitCode).toBe(0);
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy.mock.calls[0][0]).toMatchObject({
      audioPath,
      outputPath: output,
      model: "demo-model"
    });
  });
});
