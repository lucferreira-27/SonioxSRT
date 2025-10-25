import { describe, expect, it } from "vitest";

import {
  RealTimeResult,
  buildRealtimeConfig,
  renderTokens
} from "../src/realtime";

describe("realtime helpers", () => {
  it("buildRealtimeConfig accepts preview v2 model", () => {
    const config = buildRealtimeConfig({
      apiKey: "dummy",
      model: "stt-rt-preview-v2",
      languageHints: ["en", "es"],
      enableLanguageIdentification: true,
      enableSpeakerDiarization: true,
      context: "Example context"
    });

    expect(config.model).toBe("stt-rt-preview-v2");
    expect(config.language_hints).toEqual(["en", "es"]);
    expect(config.enable_language_identification).toBe(true);
    expect(config.enable_speaker_diarization).toBe(true);
    expect(config.context).toBe("Example context");
  });

  it("renderTokens adds speaker and language tags", () => {
    const finalTokens = [
      { text: "Hello", is_final: true, speaker: "A", language: "en" }
    ];
    const nonFinalTokens = [
      {
        text: " mundo",
        is_final: false,
        language: "es",
        translation_status: "translation"
      }
    ];

    const rendered = renderTokens(finalTokens, nonFinalTokens);

    expect(rendered).toContain("Speaker A:");
    expect(rendered).toContain("[en]");
    expect(rendered).toContain("[Translation] [es]");
    expect(rendered.trim().endsWith("===============================")).toBe(true);
  });

  it("RealTimeResult toTranscript mirrors tokens", () => {
    const result = new RealTimeResult("stt-rt-preview-v2", [
      { text: "Hello", is_final: true },
      { text: " world", is_final: true }
    ], [{ sequence_id: 1 }]);

    const transcript = result.toTranscript();
    expect(transcript.model).toBe("stt-rt-preview-v2");
    expect(transcript.tokens).toEqual(result.finalTokens);
    expect(transcript.responses).toEqual([{ sequence_id: 1 }]);
    expect(`${transcript.text}`.startsWith("Hello")).toBe(true);
  });
});
