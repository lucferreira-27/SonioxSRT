import axios, { AxiosInstance } from "axios";
import FormData from "form-data";
import fs from "node:fs";
import path from "node:path";
import { setTimeout as sleep } from "node:timers/promises";
import dotenv from "dotenv";

export const DEFAULT_BASE_URL = "https://api.soniox.com";
export const DEFAULT_POLL_INTERVAL = 1.0;

export class SonioxError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SonioxError";
  }
}

function loadEnvFile(filePath: string): void {
  try {
    const content = fs.readFileSync(filePath, "utf-8");
    const parsed = dotenv.parse(content);
    for (const [key, value] of Object.entries(parsed)) {
      if (process.env[key] === undefined) {
        process.env[key] = value;
      }
    }
  } catch {
    // ignore missing/invalid files
  }
}

function candidateEnvPaths(
  extraPaths?: string[]
): string[] {
  const seen = new Set<string>();
  const add = (p: string): void => {
    const resolved = path.resolve(p);
    if (!seen.has(resolved)) {
      seen.add(resolved);
    }
  };

  if (extraPaths) {
    for (const p of extraPaths) {
      add(p);
    }
  }

  add(path.join(process.cwd(), ".env"));

  const packageRoot = path.resolve(__dirname, "..");
  add(path.join(packageRoot, ".env"));
  add(path.join(path.dirname(packageRoot), ".env"));

  return Array.from(seen);
}

export function requireApiKey(
  envVar = "SONIOX_API_KEY",
  options?: { searchPaths?: string[] }
): string {
  let apiKey = process.env[envVar];
  if (!apiKey) {
    for (const envPath of candidateEnvPaths(options?.searchPaths)) {
      if (fs.existsSync(envPath)) {
        loadEnvFile(envPath);
        apiKey = process.env[envVar];
        if (apiKey) {
          break;
        }
      }
    }
  }

  if (!apiKey) {
    throw new Error(
      `${envVar} is not set.\n` +
        "Create an API key in the Soniox Console and export it:\n" +
        `  export ${envVar}=<YOUR_API_KEY>`
    );
  }
  return apiKey;
}

export class SonioxClient {
  private readonly client: AxiosInstance;

  constructor(
    private readonly apiKey: string,
    private readonly baseUrl: string = DEFAULT_BASE_URL
  ) {
    this.client = axios.create({
      baseURL: this.baseUrl,
      headers: {
        Authorization: `Bearer ${this.apiKey}`
      },
      timeout: 120_000
    });
  }

  close(): void {
    // Axios does not require explicit closing, but the method keeps API parity.
  }

  async uploadFile(audioPath: string): Promise<string> {
    const resolved = path.resolve(audioPath);
    const form = new FormData();
    form.append("file", fs.createReadStream(resolved));

    const response = await this.client.post("/v1/files", form, {
      headers: form.getHeaders()
    });

    if (![200, 201, 202].includes(response.status)) {
      throw new SonioxError(`File upload failed: ${response.statusText}`);
    }

    const fileId = (response.data?.id ?? "") as string;
    if (!fileId) {
      throw new SonioxError(
        `Unexpected upload response: ${JSON.stringify(response.data)}`
      );
    }
    return fileId;
  }

  async deleteFile(fileId: string): Promise<void> {
    const response = await this.client.delete(`/v1/files/${fileId}`);
    if (![200, 204].includes(response.status)) {
      throw new SonioxError(
        `Failed to delete file ${fileId}: ${response.statusText}`
      );
    }
  }

  async createTranscription(options: {
    model: string;
    fileId?: string | null;
    audioUrl?: string | null;
    extraOptions?: Record<string, unknown>;
  }): Promise<string> {
    const { model, fileId, audioUrl, extraOptions } = options;
    if (!fileId && !audioUrl) {
      throw new Error("Specify either fileId or audioUrl.");
    }

    const payload: Record<string, unknown> = { model };
    if (fileId) {
      payload.file_id = fileId;
    }
    if (audioUrl) {
      payload.audio_url = audioUrl;
    }
    if (extraOptions) {
      Object.assign(payload, extraOptions);
    }

    const response = await this.client.post("/v1/transcriptions", payload);
    if (![200, 201, 202].includes(response.status)) {
      throw new SonioxError(
        `Create transcription failed: ${response.statusText}`
      );
    }
    const transcriptionId = (response.data?.id ?? "") as string;
    if (!transcriptionId) {
      throw new SonioxError(
        `Unexpected transcription response: ${JSON.stringify(response.data)}`
      );
    }
    return transcriptionId;
  }

  async waitForCompletion(
    transcriptionId: string,
    pollInterval = DEFAULT_POLL_INTERVAL
  ): Promise<void> {
    const statusPath = `/v1/transcriptions/${transcriptionId}`;
    while (true) {
      const response = await this.client.get(statusPath);
      if (response.status !== 200) {
        throw new SonioxError(`Polling failed: ${response.statusText}`);
      }
      const payload = response.data ?? {};
      const status = payload.status as string | undefined;
      if (status === "completed") {
        return;
      }
      if (status === "error") {
        const message =
          (payload.error_message as string | undefined) ?? "unknown error";
        throw new SonioxError(`Transcription failed: ${message}`);
      }
      await sleep(pollInterval * 1000);
    }
  }

  async fetchTranscript(transcriptionId: string): Promise<Record<string, any>> {
    const response = await this.client.get(
      `/v1/transcriptions/${transcriptionId}/transcript`
    );
    if (response.status !== 200) {
      throw new SonioxError(`Fetching transcript failed: ${response.statusText}`);
    }
    return response.data as Record<string, any>;
  }

  async deleteTranscription(transcriptionId: string): Promise<void> {
    const response = await this.client.delete(
      `/v1/transcriptions/${transcriptionId}`
    );
    if (![200, 204].includes(response.status)) {
      throw new SonioxError(
        `Failed to delete transcription ${transcriptionId}: ${response.statusText}`
      );
    }
  }
}

export default SonioxClient;
