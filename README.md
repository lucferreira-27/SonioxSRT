# SonioxSRT

SonioxSRT provides helper libraries and CLIs for working with the Soniox async
transcription API and generating SRT subtitles. This repository now hosts
parallel implementations in Python and TypeScript that share common samples and
documentation.

## Layout

- `python/` – original Python implementation, CLI tools, and pytest suite.
- `ts/` – TypeScript port with equivalent API surface, CLIs, and Vitest suite.
- `samples/` – shared audio and transcript fixtures used by both languages.

## Getting Started

- **Python users:** head to [`python/README.md`](python/README.md) for setup,
  CLI usage, and library examples.
- **TypeScript users:** see [`ts/README.md`](ts/README.md) for npm installation,
  CLI commands, and API usage in Node.js projects.

Both implementations look for a `SONIOX_API_KEY` environment variable and fall
back to loading `.env` files located at the repository root.
