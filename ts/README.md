# SonioxSRT (TypeScript)

**Purpose**: TypeScript port of the Soniox async transcription helpers and SRT
generation utilities.

**Prerequisites**: Node.js 18+ (or compatible runtime)

**Installation**
```sh
npm install sonioxsrt
```

**Local Development**
```sh
cd ts
npm install
```

**Environment**: Create a `.env` file at the repository root or export
`SONIOX_API_KEY` in your shell. The TypeScript implementation automatically
loads `.env` if the environment variable is missing.

**CLI**
- `npm run cli:transcribe -- --audio ../samples/audio.mp3 --output ../samples/response.json`
- `npm run cli:to-srt -- --input ../samples/response.json --output subtitles.srt --segment-on-sentence --line-split-delimiters .`

**Library**
```ts
import {
  SubtitleConfig,
  tokensToSubtitleSegments,
  renderSegments,
  writeSrtFile,
  srt,
  runRealtimeSession
} from "sonioxsrt";
import transcript from "../samples/response.json" assert { type: "json" };

const tokens = transcript.tokens ?? [];
const config = new SubtitleConfig({ splitOnSpeaker: true, segmentOnSentence: true, lineSplitDelimiters: ["."] });
const segments = tokensToSubtitleSegments(tokens, config);
const entries = renderSegments(segments, config);
writeSrtFile(entries, "subtitles.srt");

// Or rely on the convenience helper:
srt("../samples/response.json", "subtitles.srt");

// Stream audio via the realtime WebSocket API (requires `npm install ws` at runtime).
const realtime = await runRealtimeSession({
  audioPath: "../samples/audio.mp3",
  model: "stt-rt-preview-v2",
  languageHints: ["en"],
  enableLanguageIdentification: true
});
console.log(realtime.text);
```

**Testing**
```sh
cd ts
npm test
```

**Building**
```sh
npm run build
```

This emits compiled JavaScript and declaration files in `dist/` suitable for
publishing to npm.
