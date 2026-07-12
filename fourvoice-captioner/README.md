# FourVoice Captioner

**Four tones. One clip. Zero guesswork.**

AI-powered video captioning system that generates four stylistically distinct captions for any video clip using a multi-stage pipeline built on [Fireworks AI](https://fireworks.ai).

---

## Quick Start

### Prerequisites

- **Python 3.11+** with `pip`
- **Node.js 20+** with `npm`
- **ffmpeg** installed and on PATH
- **Fireworks AI API key** ([get one here](https://fireworks.ai))

### Setup

```bash
# Clone and enter the project
cd fourvoice-captioner

# Create .env from template
cp .env.example .env
# Edit .env and add your FIREWORKS_API_KEY

# Install dependencies
pip install -r requirements.txt
npm install
```

### Run the Web Demo

```bash
npm run dev
# Open http://localhost:3000
```

### Run Batch Mode (CLI)

```bash
# Process all videos in a directory
python fourvoice_captioner.py --input-dir ./input --output ./output/results.json
```

---

## Docker

### Build

```bash
docker build -t fourvoice-captioner .
```

### Run - Batch Mode (Hackathon Harness)

The default entrypoint runs the batch CLI pipeline. Mount your video directory to `/input` and collect results from `/output`:

```bash
docker run \
  --env-file .env \
  -v /path/to/videos:/input \
  -v /path/to/output:/output \
  fourvoice-captioner
```

This produces `/output/results.json` with captions for all video files found in `/input`.

### Run - Web Demo

Pass `web` as the command argument to start the interactive web UI:

```bash
docker run \
  --env-file .env \
  -p 3000:3000 \
  fourvoice-captioner web
```

Open `http://localhost:3000` to use the drag-and-drop interface.

> **Security note:** API keys are never baked into the Docker image. Always pass credentials at runtime via `--env-file` or `-e` flags.

---

## Architecture

```
User uploads video
        |
        v
  Node/Express Server (server.ts)
        |
        |-- Preset demo clip? --> Return cached results instantly
        |
        |-- Real upload? --> Spawn Python subprocess
                                    |
                                    v
                          fourvoice_captioner.py
                                    |
              +---------+-----------+-----------+---------+
              |         |           |           |         |
           Stage 1   Stage 2    Stage 3     Stage 4   Stage 5-8
           Audio     Audio      Factual     4-Style   QC, Recommend,
           Extract   Check      Description  Captions  Confidence,
           + STT     (>15 words  (Audio or    Generate  Output JSON
           (Whisper)  diverse?)   Vision)
```

### Pipeline Stages

| Stage | Name | Model | Purpose |
|-------|------|-------|---------|
| 1 | Audio Extraction + STT | Whisper v3 | Extract and transcribe speech |
| 2 | Audio Informativeness | (heuristic) | Check word count + diversity |
| 3A | Audio-Grounded Description | DeepSeek V4 Pro | Factual summary from transcript |
| 3B | Vision-Grounded Description | Kimi K2 (kimi-k2p6) | Factual summary from video frames |
| 4 | Four-Style Generation | DeepSeek V4 Pro | Formal, Sarcastic, Tech Humor, Non-Tech Humor |
| 5 | Self-QC Pass | DeepSeek V4 Pro | Score each caption, regenerate if needed |
| 6 | Best-Fit Recommendation | DeepSeek V4 Pro | Pick the most natural tone |
| 7 | Confidence Scoring | (heuristic) | Audio-based = higher confidence |
| 8 | Output Assembly | -- | Compile final JSON |

---

## Design Decisions

### 1. Audio-First Branching

The pipeline prioritizes spoken audio (Stage 2) as the primary signal source because human speech provides the most reliable grounding for caption generation. Videos with clear dialogue (>15 words, >40% word diversity) route through the audio-grounded path, yielding higher confidence scores. Only when audio is absent, insufficient, or repetitive (lyrics detection) does the system fall back to vision-based analysis.

### 2. Self-QC with Regeneration

Stage 5 implements an automated quality control loop where each caption is scored on factual accuracy and tone accuracy using the same LLM. Captions scoring below 3/5 on either axis are automatically regenerated with a stricter prompt. This prevents hallucinated details and ensures each tone is genuinely distinct rather than superficially varied.

### 3. Four Distinct Voices

Rather than generating a single "best" caption, FourVoice produces four stylistically independent options because different audiences and platforms demand different tones. The recommendation engine (Stage 6) suggests the best fit, but the user always has all four to choose from -- critical for creators publishing across platforms with different audience expectations.

### 4. Containerized Dual-Mode Architecture

The Dockerfile supports two distinct execution modes via a single image: batch CLI mode (for automated hackathon evaluation) and web server mode (for interactive demos). This avoids the common pitfall of building a demo that cannot be evaluated, or an evaluable pipeline with no user-facing interface. The batch mode produces deterministic JSON output; the web mode adds real-time status updates and a visual results interface.

### 5. Fireworks-Only Inference

All AI inference routes exclusively through Fireworks AI APIs. The system uses a deliberate two-model architecture:

- **Whisper v3** (via Fireworks' dedicated audio endpoint at `audio-prod.api.fireworks.ai`) handles speech-to-text transcription.
- **Kimi K2** (`kimi-k2p6`) handles vision grounding (Stage 3B) — a serverless multimodal VLM that analyzes extracted video frames to produce factual scene descriptions.
- **DeepSeek V4 Pro** (`deepseek-v4-pro`) handles all text-only stages: audio-grounded description (Stage 3A), four-style caption generation (Stage 4), self-QC scoring (Stage 5), and tone recommendation (Stage 6).

This separation ensures the vision model focuses on accurate visual observation while the text model handles creative styling and quality control — preventing the common pitfall of a single model conflating description with editorialization.

---

## Differentiation

- **Multi-modal branching**: Automatically selects audio or vision grounding based on content analysis, not user configuration
- **Built-in QC loop**: Self-validates and regenerates low-quality captions before returning results
- **Four genuine tones**: Each style is independently prompted and verified, not post-hoc rewrites of a single caption
- **Production-ready containerization**: Single Docker image supports both automated evaluation and interactive demo
- **Zero external dependencies beyond Fireworks**: No Google, OpenAI, or other provider APIs -- fully portable

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FIREWORKS_API_KEY` | Yes | Your Fireworks AI API key |
| `FIREWORKS_BASE_URL` | No | API base URL (default: `https://api.fireworks.ai/inference/v1`) |
| `WHISPER_BASE_URL` | No | Whisper audio endpoint (default: `https://audio-prod.api.fireworks.ai/v1`) |
| `WHISPER_MODEL` | No | Whisper model ID (default: `whisper-v3`) |
| `VISION_MODEL` | No | Vision grounding model (default: `accounts/fireworks/models/kimi-k2p6`) |
| `STYLE_TEXT_MODEL` | No | Style generation model (default: `accounts/fireworks/models/deepseek-v4-pro`) |
| `PORT` | No | Web server port (default: `3000`) |
| `NODE_ENV` | No | Set to `production` for built assets |

---

## Project Structure

```
fourvoice-captioner/
  fourvoice_captioner.py   # Core Python pipeline (8 stages)
  server.ts                # Node/Express API server
  Dockerfile               # Dual-mode container
  package.json             # Node dependencies
  requirements.txt         # Python dependencies
  .env.example             # Environment template
  .gitignore               # Security: excludes .env, API_KEY.txt
  index.html               # HTML entry point
  vite.config.ts           # Vite build config
  tsconfig.json            # TypeScript config
  src/
    main.tsx               # React entry
    App.tsx                # 3-screen SPA (Upload/Processing/Results)
    index.css              # Design system + Tailwind
    types.ts               # TypeScript interfaces
    components/
      WaveformCanvas.tsx   # WebGL waveform shader animation
```

---

## Security & Environment Variables

This project requires API keys that must **never** be committed to version control.

### Required Variables

| Variable | Description |
|----------|-------------|
| `FIREWORKS_API_KEY` | Your Fireworks AI API key ([get one here](https://fireworks.ai)) |
| `FIREWORKS_BASE_URL` | API base URL (defaults to `https://api.fireworks.ai/inference/v1`) |

### Setup

```bash
# Copy the template (contains placeholder values only)
cp .env.example .env

# Edit .env and fill in your real API key
# NEVER commit .env — it is excluded via .gitignore
```

### Optional Model Overrides

Set these in `.env` to override default model choices:
- `VISION_MODEL` — VLM for frame analysis (default: `kimi-k2p6`)
- `GROUNDING_TEXT_MODEL` — text model for grounding (default: `deepseek-v4-pro`)
- `STYLE_TEXT_MODEL` — text model for caption generation (default: `deepseek-v4-pro`)
- `JUDGE_TEXT_MODEL` — text model for QC/verification (default: `deepseek-v4-pro`)

> ⚠️ If you find a hardcoded key anywhere in this codebase, it is a bug. Please report it.

---

## License

Built for AMD Developer Hackathon ACT II, Track 2 (Video Captioning).
