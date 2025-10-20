# SonioxSRT

SonioxSRT provides helper libraries and CLIs for working with the Soniox async
transcription API and generating SRT subtitles. The repository hosts parallel
implementations in Python and TypeScript that share common samples and tests.

## Repository Layout

- `python/` – Python package, CLI entry points, and pytest suite.
- `ts/` – TypeScript port with equivalent APIs, CLIs, and Vitest coverage.
- `samples/` – Shared audio/transcript fixtures used by both stacks.

## Quick Start

1. Export your Soniox API key (or add it to a `.env` file in the repo root):
   ```sh
   export SONIOX_API_KEY=<YOUR_API_KEY>
   ```
2. Pick the language you want to use:
   - Python instructions live in [`python/README.md`](python/README.md).
   - TypeScript instructions live in [`ts/README.md`](ts/README.md).

Both implementations load the shared fixtures from `samples/` and expose CLIs for
transcribing audio and emitting SRT files.

### Basic Usage

**Python**
```python
from pathlib import Path
from sonioxsrt import srt

# Convert the shared sample transcript into subtitles
srt(Path("../samples/response.json"), output_path="subtitles.srt")
print("SRT ready at subtitles.srt")
```

**TypeScript**
```ts
import { srt } from "@lucfe/sonioxsrt";

// Convert the shared sample transcript into subtitles
srt("../samples/response.json", "subtitles.srt");
console.log("SRT ready at subtitles.srt");
```

## Testing Locally

- **Python**
  ```sh
  cd python
  python3 -m venv .venv
  . .venv/bin/activate
  python -m pip install -r requirements-dev.txt
  python -m pytest
  ```

- **TypeScript**
  ```sh
  cd ts
  npm install
  npm test
  ```

## Continuous Integration

GitHub Actions runs both the Python and TypeScript suites on every push and pull
request. The workflow definition lives at
[`./.github/workflows/tests.yml`](.github/workflows/tests.yml).
