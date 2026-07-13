# FourVoice Captioner

Fully autonomous, containerized Python pipeline for **AMD Developer Hackathon ACT II — Track 2 (Video Captioning)**. Processes short video clips and outputs four distinct styled captions per clip: `formal`, `sarcastic`, `humorous_tech`, and `humorous_non_tech`.

Unlike template-based four-style generators, this agent (1) grounds facts once via an audio-first/vision-fallback branch that correctly handles dialogue, music, and static-image content without hallucination, (2) self-critiques its own captions against the source facts before finalizing, (3) flags which of the four tones is the most natural fit for each specific clip with reasoning, and (4) reports its own per-clip confidence — showing genuine content understanding rather than four independent guesses.

## Quick Start

> **Security Note:** Never commit `.env` files containing real API keys to the repository. The `.gitignore` is configured to exclude them. Always copy `.env.example` to `.env` and fill in your real values locally.

### Prerequisites

- Python 3.11+
- `ffmpeg` on PATH
- Fireworks API key (`FIREWORKS_API_KEY`)

### Environment

Copy [`.env.example`](.env.example) to `.env` and set your key:

```bash
FIREWORKS_API_KEY=your_key_here
FIREWORKS_BASE_URL=https://api.fireworks.ai/inference/v1
```

Verify models against the live catalog:

```bash
python fourvoice-captioner/scripts/verify_fireworks_models.py
```

### Hackathon mode (`/input/tasks.json`)

Evaluator mounts:

```text
/input/tasks.json   →  video URLs + task_ids
/output/results.json
```

```powershell
docker buildx build --platform linux/amd64 -t fourvoice-captioner:latest --load .
docker run --rm --platform linux/amd64 --env-file .env `
  -v "${PWD}\sample_input:/input:ro" `
  -v "${PWD}\sample_output:/output" `
  fourvoice-captioner: latest
```

### Folder mode (local video files)

Place `.mp4`/`.mov`/`.mkv` files in a folder. If `tasks.json` is absent, the pipeline scans the directory automatically:

```powershell
$env:INPUT_DIR = ".\sample_videos"
$env:OUTPUT_DIR = ".\sample_output"
$env:OUTPUT_PATH = ".\sample_output\results.json"
python fourvoice-captioner\fourvoice_captioner.py
```

Folder mode also writes one JSON per clip under `OUTPUT_DIR`.

### Dry run (no API credits)

```powershell
$env:DRY_RUN = "1"
python fourvoice-captioner\fourvoice_captioner.py --input-dir .\sample_videos --output .\sample_output\results.json
```

## Pipeline Stages

| Stage | Description |
|-------|-------------|
| 0 | Auto-detect `tasks.json` vs video folder; per-video error isolation |
| 1 | ffmpeg audio extract → Fireworks |
| 2 | Informativeness branch (>15 words, diversity/repetition check) |
| 3A | Audio-grounded factual description (DeepSeek V4 Pro) |
| 3B | Vision-grounded description (9 resized frames) |
| 4 | Four separate style calls (DeepSeek V4 Pro) |
| 5 | Self-QC judge; regenerate captions scoring below 3/5 |
| 6 | Best-fit tone recommendation + reasoning |
| 7 | Confidence score (0.0–1.0) |
| 8 | Write `results.json` (incremental flush per video) |

## Output Schemas

**Hackathon** (`tasks.json` input):

```json
[
  {
    "task_id": "v1",
    "captions": {
      "formal": "...",
      "sarcastic": "...",
      "humorous_tech": "...",
      "humorous_non_tech": "..."
    },
    "recommended_style": "sarcastic",
    "reasoning": "...",
    "confidence": 0.87
  }
]
```

**Folder mode** (per-clip + aggregate):

```json
{
  "video": "clip1.mp4",
  "formal": "...",
  "sarcastic": "...",
  "humorous_tech": "...",
  "humorous_non_tech": "...",
  "recommended_style": "sarcastic",
  "reasoning": "...",
  "confidence": 0.87
}
```

## Design Decisions

### 1. Audio-first / vision-fallback branching

Stage 2 counts real spoken words (excluding timestamps/metadata) and applies a repetition check:

- **>15 words** of coherent speech
- **Unique-word ratio ≥ 0.45** (filters repetitive lyrics)
- **No single word >25% of tokens** (filters "la la la" loops)

If informative → **Stage 3A** grounds captions on the transcript alone (no invented visuals). If not → **Stage 3B** extracts 9 evenly spaced ffmpeg frames and uses Kimi K2 vision to describe what is actually visible.

### 2. Music videos and static-image reels

No special-casing is required. Music-only, silent action, and static-image-with-music clips fail the informativeness check and naturally route to vision grounding. Kimi K2 is instructed to describe visible content as-is — illustrated panels, performers, on-screen text — without guessing audio semantics from lyrics fragments.

### 3. Confidence score

`confidence` (0.0–1.0) reflects how much of the final description was directly observed vs inferred:

| Signal | Weight |
|--------|--------|
| Audio-grounded branch (3A) | +0.35 base |
| Vision-only branch (3B) | +0.20 base |
| Transcript word count (capped at 50 words) | ×0.20 |
| Unique-word ratio from Stage 2 | ×0.15 |
| Self-QC factual accuracy scores / 5 | ×0.30 |

Vision-only, ambiguous, or static clips score lower; dialogue-rich clips score higher.

## Local Testing

Run heuristic tests (no API):

```bash
python fourvoice-captioner/scripts/test_heuristics.py
```

Test matrix (supply 5 clips under `sample_videos/`):

| Clip type | Expected branch |
|-----------|-----------------|
| Dialogue-heavy | 3A audio |
| Music video | 3B vision |
| Silent action | 3B vision |
| Static-image + music | 3B vision |
| Low-audio ambiguous | 3B vision |

```powershell
.\fourvoice-captioner\scripts\run_local_test.ps1
```

## Docker Submission Checklist

- [ ] Image built for `linux/amd64`
- [ ] Image is public and `docker pull <your-image>` succeeds
- [ ] `FIREWORKS_API_KEY` passed at runtime (never committed to git)
- [ ] Container reads `/input/tasks.json` or scans `/input` for videos
- [ ] Container writes `/output/results.json`
- [ ] All four caption styles present for every task
- [ ] Container exits successfully even when individual clips fail

## Project Layout

```text
A:\AMD\
├── Dockerfile
├── README.md
├── .env.example
├── sample_input/tasks.json
└── fourvoice-captioner/
    ├── fourvoice_captioner.py
    ├── Dockerfile
    └── scripts/
        ├── verify_fireworks_models.py
        ├── test_heuristics.py
        └── run_local_test.ps1
```
