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
- `npm run cli:to-srt -- --input ../samples/response.json --output subtitles.srt`

**Library**
```ts
import { SubtitleConfig, tokensToSubtitleSegments, renderSegments, writeSrtFile, srt } from "sonioxsrt";
import transcript from "../samples/response.json" assert { type: "json" };

const tokens = transcript.tokens ?? [];
const config = new SubtitleConfig({ splitOnSpeaker: true });
const segments = tokensToSubtitleSegments(tokens, config);
const entries = renderSegments(segments, config);
writeSrtFile(entries, "subtitles.srt");

// Or rely on the convenience helper:
srt("../samples/response.json", "subtitles.srt");
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
