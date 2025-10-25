# SonioxSRT (Python)

**Purpose**: Minimal toolkit for Soniox async transcription plus SRT generation.

**Docs**:
- https://soniox.com/docs/stt/async/async-transcription.mdx
- https://soniox.com/docs/stt/get-started.mdx

**API Keys**: `export SONIOX_API_KEY=<YOUR_API_KEY>` before running any commands,
or place `SONIOX_API_KEY=...` inside a `.env` file in the repository root. For
LLM-powered translation set `LLM_API_KEY` (plus optional `LLM_BASE_URL`,
`LLM_MODEL`, and `DEFAULT_MODEL`). The CLI automatically loads `.env` files via
`python-dotenv`.

**Samples**: `../samples/audio.mp3` (input) and `../samples/response.json`
(ground truth transcript shared with the TypeScript port).

**CLI** (run from the `python/` directory)
- `python3 -m sonioxsrt.cli.transcribe --audio ../samples/audio.mp3 --output ../samples/response.json`
- `python3 -m sonioxsrt.cli.to_srt --input ../samples/response.json --output subtitles.srt`

| Command | Flag | Description | Default |
| --- | --- | --- | --- |
| `transcribe` | `--audio` | Path to local audio file | `audio.wav` |
|  | `--audio-url` | Public URL for remote audio (disables `--audio`) | — |
|  | `--model` | Soniox model identifier | `stt-async-preview` |
|  | `--output` | JSON transcript output path | `response.json` |
|  | `--keep-resources` | Leave uploaded file/transcription on Soniox | `False` |
|  | `--poll-interval` | Seconds between status polls | `1.0` |
|  | `--base-url` | Override API base URL | `https://api.soniox.com` |
| `to_srt` | `--input` | Transcript JSON path | `response.json` |
|  | `--output` | Destination SRT file | `subtitles.srt` |
|  | `--gap-ms` | Silence threshold for splitting (ms) | `1200` |
|  | `--min-dur-ms` | Minimum subtitle duration (ms) | `1000` |
|  | `--max-dur-ms` | Maximum subtitle duration (ms) | `7000` |
|  | `--max-cps` | Max characters per second | `17` |
|  | `--max-cpl` | Max characters per line | `42` |
|  | `--max-lines` | Max lines per subtitle | `2` |
|  | `--line-split-delimiters` | Preferred characters for intra-caption line breaks | — |
|  | `--segment-on-sentence` / `--no-segment-on-sentence` | Force or disable sentence-based segmentation | `True` |
|  | `--split-on-speaker` | Break on speaker change | `False` |
|  | `--ellipses` | Use ellipses for continued sentences | `False` |
|  | `--translate-to` | Translate subtitles to the specified language | — |
|  | `--translation-passes` | Use `1` (draft) or `3` (draft + review + refine) when translating | `1` |
|  | `--llm-model` | LLM model name (env `LLM_MODEL`, `DEFAULT_MODEL`, or `gpt-4o-mini`) | — |
|  | `--llm-base-url` | Override LLM API base URL (env `LLM_BASE_URL`) | — |
|  | `--llm-api-key` | Override LLM API key (env `LLM_API_KEY`) | — |

**Library**
```python
from pathlib import Path
from sonioxsrt import (
    SubtitleConfig,
    tokens_to_subtitle_segments,
    render_segments,
    write_srt_file,
    srt,
)
# Obtain tokens from a Soniox transcript JSON or API response.
tokens = ...  # transcript["tokens"]
# Configure segmentation rules.
config = SubtitleConfig(split_on_speaker=True)
# Generate segments and write using the lower-level helpers.
segments = tokens_to_subtitle_segments(tokens, config)
write_srt_file(render_segments(segments, config), "subtitles.srt")

# Or rely on the convenience helper; it accepts str, Path, or dict inputs.
# Using a string path to a JSON transcript:
srt("../samples/response.json", output_path="subtitles.srt")
# Using a Path object:
srt(Path("../samples/response.json"), output_path="subtitles.srt")
# Using an in-memory transcript dict:
srt({"tokens": tokens}, output_path="subtitles.srt")

# Stream audio over the realtime WebSocket API (requires `pip install websockets`)
from sonioxsrt import run_realtime_session

result = run_realtime_session(
    "../samples/audio.mp3",
    model="stt-rt-preview-v2",
    language_hints=["en"],
    enable_language_identification=True,
)
print(result.text)

# Convert the aggregated realtime tokens into an SRT transcript when timestamps are present.
srt(result.to_transcript(), output_path="realtime.srt")
```

**Testing**
```sh
cd python
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest
```
