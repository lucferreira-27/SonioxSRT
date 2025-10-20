import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { describe, expect, it } from "vitest";

import {
  transcribeAudio,
  transcribeAudioFile,
  transcribeAudioUrl,
  transcribeToFile
} from "../src/transcriber";
import { Transcript } from "../src/types";

const repoRoot = path.resolve(__dirname, "..", "..");
const samplesDir = path.join(repoRoot, "samples");
const transcriptPath = path.join(samplesDir, "response.json");
const transcript = JSON.parse(fs.readFileSync(transcriptPath, "utf-8")) as Transcript;

class DummyClient {
  uploadedPath?: string;
  transcriptionId = "tx-1";
  deletedTranscription?: string;
  deletedFile?: string;
  waitedFor?: string;
  audioUrlSeen?: string;
  closed = false;

  async uploadFile(audioPath: string): Promise<string> {
    this.uploadedPath = audioPath;
    return "file-1";
  }

  async createTranscription(options: {
    model: string;
    fileId?: string | null;
    audioUrl?: string | null;
    extraOptions?: Record<string, unknown>;
  }): Promise<string> {
    this.audioUrlSeen = options.audioUrl ?? undefined;
    return this.transcriptionId;
  }

  async waitForCompletion(transcriptionId: string, pollInterval: number): Promise<void> {
    this.waitedFor = transcriptionId;
  }

  async fetchTranscript(): Promise<Transcript> {
    return transcript;
  }

  async deleteTranscription(transcriptionId: string): Promise<void> {
    this.deletedTranscription = transcriptionId;
  }

  async deleteFile(fileId: string): Promise<void> {
    this.deletedFile = fileId;
  }

  close(): void {
    this.closed = true;
  }
}

describe("transcriber", () => {
  it("transcribes audio file using provided client", async () => {
    const dummy = new DummyClient();
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "sonioxsrt-ts-"));
    const audioPath = path.join(tmpDir, "clip.wav");
    fs.writeFileSync(audioPath, "RIFF");

    const result = await transcribeAudioFile(audioPath, {
      client: dummy as unknown as any
    });

    expect(result).toEqual(transcript);
    expect(dummy.uploadedPath).toBe(path.resolve(audioPath));
    expect(dummy.waitedFor).toBe(dummy.transcriptionId);
    expect(dummy.deletedTranscription).toBe(dummy.transcriptionId);
    expect(dummy.deletedFile).toBe("file-1");
    expect(dummy.closed).toBe(false);
  });

  it("transcribes via URL and keeps resources when requested", async () => {
    const dummy = new DummyClient();

    const result = await transcribeAudioUrl("https://example.com/audio.mp3", {
      client: dummy as unknown as any,
      keepRemote: true
    });

    expect(result).toEqual(transcript);
    expect(dummy.uploadedPath).toBeUndefined();
    expect(dummy.audioUrlSeen).toBe("https://example.com/audio.mp3");
    expect(dummy.deletedTranscription).toBeUndefined();
  });

  it("writes transcript to disk", async () => {
    const dummy = new DummyClient();
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "sonioxsrt-ts-"));
    const output = path.join(tmpDir, "response.json");

    const result = await transcribeToFile({
      audioUrl: "https://example.com/audio.mp3",
      outputPath: output,
      client: dummy as unknown as any
    });

    expect(result).toEqual(transcript);
    const content = JSON.parse(fs.readFileSync(output, "utf-8"));
    expect(content).toEqual(transcript);
  });

  it("requires either audio path or URL", async () => {
    await expect(transcribeAudio({})).rejects.toThrowError();
  });
});
