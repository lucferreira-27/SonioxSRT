import fs from "node:fs";
import path from "node:path";

import {
  DEFAULT_BASE_URL,
  DEFAULT_POLL_INTERVAL,
  SonioxClient,
  SonioxError,
  requireApiKey
} from "./api";

export interface TranscribeOptions {
  audioPath?: string;
  audioUrl?: string;
  model?: string;
  extraOptions?: Record<string, unknown>;
  pollInterval?: number;
  keepRemote?: boolean;
  client?: SonioxClient;
  baseUrl?: string;
  searchEnvPaths?: string[];
}

async function ensureClient(
  maybeClient: SonioxClient | undefined,
  baseUrl?: string,
  searchEnvPaths?: string[]
): Promise<{ client: SonioxClient; ownsClient: boolean }> {
  if (maybeClient) {
    return { client: maybeClient, ownsClient: false };
  }
  const apiKey = requireApiKey("SONIOX_API_KEY", { searchPaths: searchEnvPaths });
  const client = new SonioxClient(apiKey, baseUrl ?? DEFAULT_BASE_URL);
  return { client, ownsClient: true };
}

export async function transcribeAudio(options: TranscribeOptions): Promise<Record<string, any>> {
  const {
    audioPath,
    audioUrl,
    model = "stt-async-preview",
    extraOptions,
    pollInterval = DEFAULT_POLL_INTERVAL,
    keepRemote = false,
    client: providedClient,
    baseUrl,
    searchEnvPaths
  } = options;

  if (!audioPath && !audioUrl) {
    throw new Error("Specify either audioPath or audioUrl.");
  }

  let resolvedPath: string | undefined;
  if (audioPath) {
    const fullPath = path.resolve(audioPath);
    if (!fs.existsSync(fullPath)) {
      throw new Error(`Audio file not found: ${fullPath}`);
    }
    resolvedPath = fullPath;
  }

  const { client, ownsClient } = await ensureClient(providedClient, baseUrl, searchEnvPaths);

  let fileId: string | undefined;
  let transcriptionId: string | undefined;

  try {
    if (resolvedPath) {
      console.info(`Uploading audio file ${resolvedPath}`);
      fileId = await client.uploadFile(resolvedPath);
    }

    console.info(
      `Creating transcription job (model=${model}, fileId=${fileId ?? "None"}, audioUrl=${audioUrl ?? "None"})`
    );
    transcriptionId = await client.createTranscription({
      model,
      fileId,
      audioUrl,
      extraOptions
    });

    console.info(`Waiting for transcription ${transcriptionId} to complete`);
    await client.waitForCompletion(transcriptionId, pollInterval);

    console.info(`Fetching transcript ${transcriptionId}`);
    const transcript = await client.fetchTranscript(transcriptionId);
    return transcript;
  } finally {
    if (!keepRemote) {
      if (transcriptionId) {
        try {
          console.info(`Deleting remote transcription ${transcriptionId}`);
          await client.deleteTranscription(transcriptionId);
        } catch (error) {
          if (error instanceof SonioxError) {
            console.warn(
              `Failed to delete transcription ${transcriptionId}: ${error.message}`
            );
          } else {
            console.warn(`Failed to delete transcription ${transcriptionId}`);
          }
        }
      }

      if (fileId) {
        try {
          console.info(`Deleting uploaded file ${fileId}`);
          await client.deleteFile(fileId);
        } catch (error) {
          if (error instanceof SonioxError) {
            console.warn(`Failed to delete file ${fileId}: ${error.message}`);
          } else {
            console.warn(`Failed to delete file ${fileId}`);
          }
        }
      }
    }

    if (ownsClient) {
      client.close();
    }
  }
}

export async function transcribeAudioFile(
  audioPath: string,
  options: Omit<TranscribeOptions, "audioPath" | "audioUrl"> = {}
): Promise<Record<string, any>> {
  return transcribeAudio({
    audioPath,
    ...options
  });
}

export async function transcribeAudioUrl(
  audioUrl: string,
  options: Omit<TranscribeOptions, "audioPath" | "audioUrl"> = {}
): Promise<Record<string, any>> {
  return transcribeAudio({
    audioUrl,
    ...options
  });
}

export async function transcribeToFile(
  options: TranscribeOptions & { outputPath: string }
): Promise<Record<string, any>> {
  const transcript = await transcribeAudio(options);
  const outputPath = path.resolve(options.outputPath);
  console.info(`Writing transcript JSON to ${outputPath}`);
  fs.writeFileSync(outputPath, JSON.stringify(transcript, null, 2), {
    encoding: "utf-8"
  });
  return transcript;
}
