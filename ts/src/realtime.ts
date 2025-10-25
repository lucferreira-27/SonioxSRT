import fs from "node:fs";
import path from "node:path";

import { requireApiKey } from "./api";

export const SONIOX_REALTIME_URL = "wss://stt-rt.soniox.com/transcribe-websocket";
export const DEFAULT_REALTIME_MODEL = "stt-rt-preview";
export const SUPPORTED_REALTIME_MODELS = [
  DEFAULT_REALTIME_MODEL,
  "stt-rt-preview-v2"
] as const;
export const DEFAULT_AUDIO_CHUNK_SIZE = 3840;
export const DEFAULT_AUDIO_SLEEP_MS = 120;

export type RealTimeToken = Record<string, any>;

export interface RealTimeUpdate {
  text: string;
  finalTokens: RealTimeToken[];
  nonFinalTokens: RealTimeToken[];
  raw: Record<string, any>;
}

export class RealTimeResult {
  constructor(
    public readonly model: string,
    public readonly finalTokens: RealTimeToken[],
    public readonly responses: Record<string, any>[]
  ) {}

  get text(): string {
    return renderTokens(this.finalTokens, []);
  }

  toTranscript(): Record<string, any> {
    return {
      model: this.model,
      tokens: this.finalTokens,
      responses: this.responses,
      text: this.text
    };
  }
}

export interface BuildRealtimeConfigOptions {
  apiKey: string;
  model?: string;
  audioFormat?: string;
  sampleRate?: number;
  numChannels?: number;
  languageHints?: string[];
  enableLanguageIdentification?: boolean;
  enableSpeakerDiarization?: boolean;
  context?: string;
  enableEndpointDetection?: boolean;
  translation?: Record<string, unknown> | "none";
  extraOptions?: Record<string, unknown>;
}

export function buildRealtimeConfig(
  options: BuildRealtimeConfigOptions
): Record<string, unknown> {
  const {
    apiKey,
    model = DEFAULT_REALTIME_MODEL,
    audioFormat = "auto",
    sampleRate,
    numChannels,
    languageHints,
    enableLanguageIdentification,
    enableSpeakerDiarization,
    context,
    enableEndpointDetection = true,
    translation,
    extraOptions
  } = options;

  const config: Record<string, unknown> = {
    api_key: apiKey,
    model
  };

  if (languageHints?.length) {
    config.language_hints = languageHints;
  }
  if (enableLanguageIdentification) {
    config.enable_language_identification = true;
  }
  if (enableSpeakerDiarization) {
    config.enable_speaker_diarization = true;
  }
  if (context) {
    config.context = context;
  }
  if (enableEndpointDetection !== undefined) {
    config.enable_endpoint_detection = enableEndpointDetection;
  }

  if (audioFormat === "auto") {
    config.audio_format = "auto";
  } else {
    config.audio_format = audioFormat;
    if (sampleRate !== undefined) {
      config.sample_rate = sampleRate;
    }
    if (numChannels !== undefined) {
      config.num_channels = numChannels;
    }
  }

  if (translation && translation !== "none") {
    config.translation = translation;
  }

  if (extraOptions) {
    Object.assign(config, extraOptions);
  }

  return config;
}

export function renderTokens(
  finalTokens: RealTimeToken[],
  nonFinalTokens: RealTimeToken[]
): string {
  const textParts: string[] = [];
  let currentSpeaker: string | undefined;
  let currentLanguage: string | undefined;

  for (const token of [...finalTokens, ...nonFinalTokens]) {
    let text = `${token.text ?? ""}`;
    if (!text) {
      continue;
    }
    const speaker = token.speaker as string | undefined;
    const language = token.language as string | undefined;
    const isTranslation = token.translation_status === "translation";

    if (speaker && speaker !== currentSpeaker) {
      if (currentSpeaker !== undefined) {
        textParts.push("\n\n");
      }
      currentSpeaker = speaker;
      currentLanguage = undefined;
      textParts.push(`Speaker ${currentSpeaker}:`);
    }

    if (language && language !== currentLanguage) {
      currentLanguage = language;
      const prefix = isTranslation ? "[Translation] " : "";
      textParts.push(`\n${prefix}[${currentLanguage}] `);
      text = text.trimStart();
    }

    textParts.push(text);
  }

  if (textParts.length > 0) {
    textParts.push("\n===============================");
  }

  return textParts.join("");
}

export interface RunRealtimeSessionOptions {
  audioPath: string;
  apiKey?: string;
  model?: string;
  audioFormat?: string;
  sampleRate?: number;
  numChannels?: number;
  languageHints?: string[];
  enableLanguageIdentification?: boolean;
  enableSpeakerDiarization?: boolean;
  context?: string;
  enableEndpointDetection?: boolean;
  translation?: Record<string, unknown> | "none";
  extraOptions?: Record<string, unknown>;
  websocketUrl?: string;
  chunkSize?: number;
  chunkSleepMs?: number;
  onUpdate?: (update: RealTimeUpdate) => void;
}

async function ensureWebSocket(): Promise<any> {
  try {
    const mod = await import("ws");
    return mod.WebSocket ?? mod.default ?? mod;
  } catch (error) {
    const depError = new Error(
      "Missing dependency: ws\nInstall it with 'npm install ws' to use realtime features."
    );
    if (error instanceof Error) {
      (depError as { cause?: Error }).cause = error;
    }
    throw depError;
  }
}

async function streamAudio(
  audioPath: string,
  ws: any,
  chunkSize: number,
  sleepMs: number
): Promise<void> {
  const resolved = path.resolve(audioPath);
  const fd = fs.openSync(resolved, "r");
  const buffer = Buffer.alloc(chunkSize);
  try {
    while (true) {
      const bytesRead = fs.readSync(fd, buffer, 0, chunkSize, null);
      if (bytesRead <= 0) {
        break;
      }
      ws.send(buffer.subarray(0, bytesRead));
      if (sleepMs > 0) {
        await new Promise((res) => setTimeout(res, sleepMs));
      }
    }
    ws.send("");
  } finally {
    fs.closeSync(fd);
  }
}

export async function runRealtimeSession(
  options: RunRealtimeSessionOptions
): Promise<RealTimeResult> {
  const {
    audioPath,
    apiKey = requireApiKey(),
    model = DEFAULT_REALTIME_MODEL,
    audioFormat = "auto",
    sampleRate,
    numChannels,
    languageHints,
    enableLanguageIdentification,
    enableSpeakerDiarization,
    context,
    enableEndpointDetection = true,
    translation,
    extraOptions,
    websocketUrl = SONIOX_REALTIME_URL,
    chunkSize = DEFAULT_AUDIO_CHUNK_SIZE,
    chunkSleepMs = DEFAULT_AUDIO_SLEEP_MS,
    onUpdate
  } = options;

  if (!fs.existsSync(audioPath)) {
    throw new Error(`Audio file not found: ${audioPath}`);
  }

  const config = buildRealtimeConfig({
    apiKey,
    model,
    audioFormat,
    sampleRate,
    numChannels,
    languageHints,
    enableLanguageIdentification,
    enableSpeakerDiarization,
    context,
    enableEndpointDetection,
    translation,
    extraOptions
  });

  const WebSocketImpl = await ensureWebSocket();
  const finalTokens: RealTimeToken[] = [];
  const responses: Record<string, any>[] = [];

  return new Promise<RealTimeResult>((resolve, reject) => {
    const ws = new WebSocketImpl(websocketUrl);

    ws.on("open", () => {
      ws.send(JSON.stringify(config));
      streamAudio(audioPath, ws, chunkSize, chunkSleepMs).catch(reject);
    });

    ws.on("message", (message: Buffer) => {
      const payload = JSON.parse(message.toString()) as Record<string, any>;
      responses.push(payload);

      const errorCode = payload.error_code;
      if (errorCode !== undefined && errorCode !== null) {
        const errorMessage = payload.error_message ?? "unknown error";
        reject(
          new Error(`Realtime session error ${errorCode}: ${errorMessage}`)
        );
        ws.close();
        return;
      }

      const nonFinalTokens: RealTimeToken[] = [];
      for (const token of payload.tokens ?? []) {
        if (!token?.text) {
          continue;
        }
        if (token.is_final) {
          finalTokens.push(token);
        } else {
          nonFinalTokens.push(token);
        }
      }

      const text = renderTokens(finalTokens, nonFinalTokens);
      if (onUpdate) {
        onUpdate({
          text,
          finalTokens: [...finalTokens],
          nonFinalTokens,
          raw: payload
        });
      }

      if (payload.finished) {
        ws.close();
        resolve(new RealTimeResult(model, [...finalTokens], responses));
      }
    });

    ws.on("error", (error: Error) => {
      reject(error);
    });

    ws.on("close", () => {
      resolve(new RealTimeResult(model, [...finalTokens], responses));
    });
  });
}
