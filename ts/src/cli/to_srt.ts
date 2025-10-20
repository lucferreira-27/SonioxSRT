#!/usr/bin/env ts-node
import { Command } from "commander";
import fs from "node:fs";
import path from "node:path";
import { SubtitleConfig, srt } from "../subtitles";

const DEFAULT_CONFIG = new SubtitleConfig();

function buildCommand(): Command {
  const program = new Command();
  program
    .description("Convert a Soniox transcription JSON into an SRT subtitle file.")
    .option("--input <path>", "Path to the Soniox JSON transcript", "response.json")
    .option("--output <path>", "Path for the generated SRT file", "subtitles.srt")
    .option(
      "--gap-ms <ms>",
      "Start new subtitles when silence between tokens exceeds this gap",
      (value) => parseInt(value, 10),
      DEFAULT_CONFIG.gap_ms
    )
    .option(
      "--min-dur-ms <ms>",
      "Minimum subtitle duration in milliseconds",
      (value) => parseInt(value, 10),
      DEFAULT_CONFIG.min_dur_ms
    )
    .option(
      "--max-dur-ms <ms>",
      "Maximum subtitle duration in milliseconds",
      (value) => parseInt(value, 10),
      DEFAULT_CONFIG.max_dur_ms
    )
    .option(
      "--max-cps <value>",
      "Maximum characters-per-second for readability",
      (value) => parseFloat(value),
      DEFAULT_CONFIG.max_cps
    )
    .option(
      "--max-cpl <value>",
      "Maximum characters per line when wrapping",
      (value) => parseInt(value, 10),
      DEFAULT_CONFIG.max_cpl
    )
    .option(
      "--max-lines <value>",
      "Maximum number of lines per subtitle",
      (value) => parseInt(value, 10),
      DEFAULT_CONFIG.max_lines
    )
    .option(
      "--line-split-delimiters <chars>",
      "Prefer splitting subtitle lines after these characters when wrapping.",
      ""
    )
    .option(
      "--segment-on-sentence",
      "End subtitle entries at sentence-ending punctuation even without long silences.",
      false
    )
    .option("--split-on-speaker", "Start a new subtitle on speaker changes.", false)
    .option("--ellipses", "Use ellipses (…) to mark continued sentences.", false);
  return program;
}

async function main(argv: string[]): Promise<number> {
  const program = buildCommand();
  program.exitOverride();

  try {
    const options = program.parse(argv).opts<{
      input: string;
      output: string;
      gapMs: number;
      minDurMs: number;
      maxDurMs: number;
      maxCps: number;
      maxCpl: number;
      maxLines: number;
      lineSplitDelimiters: string;
      segmentOnSentence: boolean;
      splitOnSpeaker: boolean;
      ellipses: boolean;
    }>();

    const inputPath = path.resolve(options.input);
    if (!fs.existsSync(inputPath)) {
      throw new Error(`Input file not found: ${inputPath}`);
    }

    const lineSplitDelimiters = (options.lineSplitDelimiters ?? "")
      .split("")
      .map((value) => value.trim())
      .filter((value) => value.length > 0);

    const config = new SubtitleConfig({
      gapMs: options.gapMs,
      minDurMs: options.minDurMs,
      maxDurMs: options.maxDurMs,
      maxCps: options.maxCps,
      maxCpl: options.maxCpl,
      maxLines: options.maxLines,
      lineSplitDelimiters,
      segmentOnSentence: options.segmentOnSentence,
      splitOnSpeaker: options.splitOnSpeaker,
      ellipses: options.ellipses
    });

    srt(inputPath, options.output, config);
    console.info(
      `Wrote subtitles to ${path.resolve(options.output)}`
    );
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
    (code) => process.exit(code),
    (error) => {
      console.error(error instanceof Error ? error.message : String(error));
      process.exit(1);
    }
  );
}

export default main;
