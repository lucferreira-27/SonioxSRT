#!/usr/bin/env ts-node
import { Command } from "commander";
import fs from "node:fs";
import path from "node:path";
import { DEFAULT_BASE_URL, DEFAULT_POLL_INTERVAL } from "../api";
import { transcribeToFile } from "../transcriber";

function buildCommand(): Command {
  const program = new Command();
  program
    .description("Submit audio to Soniox and save the JSON transcript.")
    .option(
      "--audio <path>",
      "Path to the local audio file to transcribe",
      "audio.wav"
    )
    .option(
      "--audio-url <url>",
      "Optional public URL of the audio file instead of --audio."
    )
    .option(
      "--model <name>",
      "Soniox model to use",
      "stt-async-preview"
    )
    .option(
      "--output <path>",
      "Path to save the JSON response",
      "response.json"
    )
    .option("--keep-resources", "Skip deleting the uploaded file and transcription on Soniox.", false)
    .option(
      "--poll-interval <seconds>",
      "Seconds between status polls",
      (value) => parseFloat(value),
      DEFAULT_POLL_INTERVAL
    )
    .option("--base-url <url>", "Override the Soniox API base URL", DEFAULT_BASE_URL);
  return program;
}

async function main(argv: string[]): Promise<number> {
  const program = buildCommand();
  program.exitOverride();

  try {
    const options = program.parse(argv).opts<{
      audio: string;
      audioUrl?: string;
      model: string;
      output: string;
      keepResources: boolean;
      pollInterval: number;
      baseUrl: string;
    }>();

    if (!options.audioUrl && !options.audio) {
      throw new Error("Provide either --audio or --audio-url.");
    }
    if (!options.audioUrl) {
      const audioPath = path.resolve(options.audio);
      if (!fs.existsSync(audioPath)) {
        throw new Error(`Audio file not found: ${audioPath}`);
      }
      console.info(`Using local audio file ${audioPath}`);
    } else {
      console.info(`Using remote audio URL ${options.audioUrl}`);
    }

    await transcribeToFile({
      audioPath: options.audioUrl ? undefined : options.audio,
      audioUrl: options.audioUrl,
      model: options.model,
      outputPath: options.output,
      pollInterval: options.pollInterval,
      keepRemote: options.keepResources,
      baseUrl: options.baseUrl
    });
    console.info(`Saved transcription JSON to ${path.resolve(options.output)}`);
    return 0;
  } catch (error) {
    if (error instanceof Error && (error as any).code === "commander.helpDisplayed") {
      return 0;
    }
    console.error(error instanceof Error ? error.message : String(error));
    return 1;
  }
}

if (require.main === module) {
  main(process.argv).then(
    (code) => {
      process.exit(code);
    },
    (err) => {
      console.error(err instanceof Error ? err.message : String(err));
      process.exit(1);
    }
  );
}

export default main;
