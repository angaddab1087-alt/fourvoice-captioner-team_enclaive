# FourVoice Captioner — Final Build Superprompt
**AMD Developer Hackathon ACT II — Track 2: Video Captioning**

---

## 0. Project Summary

Build and fix "FourVoice Captioner" — a fully functional web application that takes a real uploaded video clip (30 seconds–2 minutes) and generates four distinct styled captions: **formal, sarcastic, humorous-tech, humorous-non-tech**, plus a best-fit tone recommendation and a confidence score. It is scored by an LLM-Judge on two axes: **accuracy** (does the caption correctly describe what's in the clip) and **tone** (is each style genuinely, distinctly that style). Every design and engineering decision below exists to maximize both axes honestly — no shortcuts, no fabricated results, no attempts to game the judge.

This is a **competition submission**, not a commercial product. No pricing, no payment language, no "Get Started"/"Buy"/"Subscribe" anywhere. All Fireworks-routed. Free, functional, demo-oriented framing throughout.

---

## 1. Critical Fixes Required (from code review — apply these first)

The existing codebase has three blocking issues that must be fixed before anything else:

### Fix 1 — Missing Dockerfile
There is currently no `Dockerfile` anywhere in the project. Without one, the submission cannot be containerized, pulled, or scored at all (`PULL_ERROR`).
- Create a `Dockerfile` at project root using a Python base image (e.g. `python:3.11-slim`).
- Install `ffmpeg` via `apt-get update && apt-get install -y ffmpeg`.
- Copy `requirements.txt`, install dependencies via pip.
- Copy `fourvoice_captioner.py` and all supporting files.
- Set entrypoint to run the pipeline against an input directory and write to an output path.
- Must build cleanly for `linux/amd64`.
- Before submitting: run `docker build` locally, then `docker pull` your own pushed public image from a clean environment to rule out `PULL_ERROR` — this single check prevented failure for dozens of teams.

### Fix 2 — Frontend calls Gemini instead of Fireworks
`server.ts` currently imports `GoogleGenAI` from `@google/genai` and calls `gemini-3.5-flash` directly using a `GEMINI_API_KEY`. Per the hackathon rules: **"Only inference routed through Fireworks AI counts toward your score."** Any Gemini-routed calls score zero.
- Remove `GoogleGenAI` import and all `ai.models.generateContent(...)` calls entirely.
- Remove `GEMINI_API_KEY` from code and `.env.example`.
- Replace with `FIREWORKS_BASE_URL` and `FIREWORKS_API_KEY` environment variables exclusively.
- The `/api/analyze` endpoint must invoke the real Python pipeline (see Fix 3), not a parallel TypeScript reimplementation calling a different provider.

### Fix 3 — Fake video analysis (filename-keyword guessing, no real processing)
For custom uploaded videos, the current code does **not** extract real audio or frames. It inspects the **filename/hint text** for keywords like "speak," "talk," "say" to guess whether dialogue exists, then asks an LLM to hallucinate a description from that filename hint alone. It never touches actual video content.
- Delete this keyword-guessing logic (`isDialogueHint`, `videoHint` heuristics) entirely.
- On upload, the Node/Express server must: save the uploaded file to a temp path → invoke the real Python pipeline (`fourvoice_captioner.py`'s processing logic) as a subprocess or via a lightweight FastAPI/Flask microservice wrapper → return the pipeline's real JSON output to the frontend.
- The 5 existing `PRESET_CLIPS` sample entries may remain as pre-computed demo examples for instant UI preview, but must be clearly labeled "sample" in the UI — any genuinely uploaded video must go through real transcription/frame extraction, never fabricated from filename text.

---

## 2. Backend Pipeline Architecture

The core pipeline in `fourvoice_captioner.py` is correct and must be preserved — do not replace real ffmpeg/Fireworks logic with simulated results.

### Stage 0 — Input handling
Accept a folder of video files (the harness provides a fixed clip set); do not hardcode filenames, iterate over whatever is present. Process each video independently. Never let one bad file crash the whole run — catch exceptions per-video, log the error, continue the batch, and fall back to a safe default output for that video rather than halting.

### Stage 1 — Audio transcription
Extract the audio track with ffmpeg. Transcribe using **Whisper v3 Turbo** via Fireworks AI (fast, cheap, supports word/sentence-level timestamps and voice-activity signals). Count real spoken words in the transcript, excluding timestamps/metadata.

### Stage 2 — Audio-informativeness check (single branch decision point)
Determine if the transcript is informative enough to ground captions on its own:
- More than ~15 real words of coherent spoken narration/dialogue, AND
- Not dominated by repetitive/lyrical content (word-diversity ratio check, threshold ~0.40, to distinguish real narration from song lyrics).

If informative → Stage 3A. If not informative (silence, music-only, ambient noise, static-image-with-music reels) → Stage 3B.

This single branch correctly handles every content type: dialogue-heavy clips, YouTuber narration, music videos, silent action clips, and static-image comic-style reels — no further special-casing needed anywhere else in the pipeline.

### Stage 3A — Audio-grounded factual description
Send the transcript to a Fireworks chat model: *"Based on this transcript, write a neutral, factual, detailed description of what is happening in this video clip. State only what is directly evidenced by the transcript. Do not invent visual details you cannot know from audio alone."*

### Stage 3B — Vision-grounded factual description
Extract 8–10 evenly spaced frames with ffmpeg. Send frames (plus any partial transcript, e.g. song lyric fragments) to a **Fireworks-hosted Gemma vision-multimodal model** (confirm exact current model ID from Fireworks' live catalog at build time — do not hardcode a possibly-stale ID). Instruction: *"Describe factually and neutrally what is visible across these frames: setting, subjects, actions, any on-screen text or style (illustrated/comic panel vs. live action). Do not guess or hallucinate anything not visibly present. If this appears to be a music/performance video or a static image with background music, describe the visual content as-is."*

Using Gemma here is deliberate — strong visual grounding, and it qualifies the project for Track 2's **"Best Use of Gemma" $3,000 partner prize**.

### Stage 4 — Four-style caption generation
Using ONLY the Stage 3A/3B factual description (never re-analyzing raw audio/video here), generate all four styles — ideally bundled into a single structured-JSON-schema call to a Fireworks chat model (a Kimi K2 or Qwen text variant — deliberately different from the Gemma grounding model, since expressive/creative writing benefits from a differently-tuned model). Document this two-model reasoning explicitly in the README.

Style instructions:
- **Formal**: neutral, professional, factual, third-person, 1–2 sentences, no opinion, no humor.
- **Sarcastic**: dry wit, ironic, under 25 words, never cruel, must stay clearly connected to actual clip content.
- **Humorous-tech**: real dev/tech-culture humor (jargon, memes, dev-life references), under 25 words, must describe what's actually happening, not a generic unrelated tech joke.
- **Humorous-non-tech**: broadly relatable everyday humor, under 25 words, no tech references, still grounded in actual clip content.

Every style prompt must explicitly state: *"Base this only on the factual description provided. Do not introduce any fact, detail, or claim not present in that description."*

### Stage 5 — Self-QC pass
One additional Fireworks call, feeding the grounded description plus all four generated captions, acting as an internal judge: score each caption 1–5 on (a) factual accuracy against the description and (b) how distinctly it matches its intended style. If any caption scores below 3/5 on either axis, regenerate that specific caption with a sharper prompt before finalizing.

### Stage 6 — Best-fit tone recommendation (differentiator)
One more Fireworks call: *"Given this factual description of the clip, which of these four tones — formal, sarcastic, humorous-tech, humorous-non-tech — best matches the clip's natural emotional register? Answer with the tone name and a one-sentence reason."* Store as `recommended_style` and `reasoning`.

### Stage 7 — Confidence scoring (differentiator)
Output a `confidence` score (0.0–1.0) per video reflecting how much of the grounded description was directly observed vs. inferred — lower for ambiguous/static/silent clips, higher for clear dialogue-rich or visually rich clips.

### Stage 8 — Output
Write structured JSON per video:
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

---

## 3. Technical Requirements

- Use `FIREWORKS_BASE_URL` and `FIREWORKS_API_KEY` strictly from environment variables — never hardcode, no Gemini/other-provider references anywhere.
- Dockerize for `linux/amd64`; ffmpeg included in the image.
- Fully autonomous batch run for the Track 2 harness — zero manual steps, processes all clips in the input folder, writes all outputs before exiting.
- Robust error handling at every stage: any single-stage failure must fall back gracefully (default confidence score, honest generic caption) rather than crashing the whole container — this one practice separated working submissions from the majority of failed ones on this hackathon's leaderboards.
- Test locally on at least 5 varied sample clips before submitting: dialogue-heavy, music-video, silent/action, static-image-with-music, low-audio-ambiguous — confirm both Stage 2 branches trigger correctly and all 4 captions per clip are genuinely stylistically distinct.

---

## 4. Frontend — Functional Application (not a landing page)

This is the actual working product interface — users upload their own video and get real results generated live. No demo-video embed anywhere; the app itself is the demonstration.

### Screens

**1. Upload screen**
- Centered drag-and-drop zone + browse fallback, 24px rounded corners, dashed amber border on drag-hover.
- Shows filename, duration, thumbnail preview once selected.
- Single action button: "Analyze Video" (pill-shaped, amber, magnetic hover).
- Plain-language line above upload zone: what happens once you upload.

**2. Processing/loading state**
- Reflects real pipeline stages dynamically, not a fixed-timer animation: "Transcribing audio…" → "Analyzing visual content…" → "Generating four styles…" → "Self-checking accuracy…" → "Finalizing…"
- Amber waveform motif animates — single line pulsing, then visibly splitting into four as Stage 4 begins.
- Thin progress line beneath the stage label.

**3. Results screen**
- Small video thumbnail/player at top (captions are the focus, not the player).
- Four caption cards via tab/toggle (FORMAL / SARCASTIC / HUMOROUS-TECH / HUMOROUS-NON-TECH, mono uppercase tracked labels), sliding underline indicator, 150ms crossfade transition, 20–24px rounded cards.
- Distinct "Recommended tone" badge/card (sage-green accent border) showing best-fit style + one-sentence reasoning, visually separated from the four standard cards.
- Confidence score as animated count-up percentage (0 → final value) with short explanatory label.
- "Analyze another video" action to reset to upload screen.

**Optional feature — Manual override / re-ask toggle:**
Include a toggle (default OFF) on the results screen, e.g. labeled "Refine manually." When OFF (default), the four AI-generated captions and the best-fit recommendation are treated as final — this is the primary path for users who trust the AI's output as-is and don't want to interact further. When toggled ON, reveal a lightweight interface allowing the user to:
- Request a re-generation of a specific style caption if it doesn't feel right, or
- Manually indicate a preferred tone different from the AI's `recommended_style` flag, triggering a targeted re-analysis for that style only.
This should be built as a genuinely optional, low-priority enhancement — implement it only after Sections 1–4's core pipeline and UI are fully working and tested. It must never be required to reach a valid results state, and its absence should not block submission if time runs short.

### Color Palette (dark, premium, non-cliché — exact hex values)
| Role | Name | Hex |
|---|---|---|
| Base background | Carbon Ink | `#0F1210` |
| Card/surface | Graphite | `#1B1F1C` |
| Primary text | Warm Bone | `#EDE9E0` |
| Bold hero accent | Signal Amber | `#F0A93E` |
| Secondary/confidence accent | muted sage | `#5FBF8C` |
| Dividers/hairlines | Charcoal Mist | `#2E332F` |

Use Signal Amber as the ONE bold color — no additional saturated accents elsewhere.

### Typography
- **Display**: Bricolage Grotesque or Space Grotesk, bold, tight tracking — 100px/72px/44px (desktop/tablet/mobile).
- **Accent**: Instrument Serif italic, used sparingly for single emphasized words within headlines only.
- **Body**: Inter or Satoshi, regular, 16–18px, 1.6+ line-height.
- **Utility/labels**: IBM Plex Mono, uppercase, 0.08em tracking — stage labels, style tags, confidence %.

### Signature Visual Element
A horizontal waveform starting as ONE unified line, then splitting into four distinct rhythmic patterns: sharp/angular (sarcastic), smooth/measured (formal), jagged/glitchy (humorous-tech), rounded/bouncy (humorous-non-tech). Rendered in Signal Amber against Carbon Ink. Appears in the loading sequence and persists with subtle idle pulsing on the results screen — never fully static.

### No background stock video/imagery needed
Since this is a functional app, skip ambient background footage entirely — the waveform motif and real functional UI carry visual interest.

### Corners
Rounded throughout — cards 20–24px, buttons pill-shaped (999px) or 16px, upload zone 24px. No sharp/squared elements anywhere.

### Micro-animations
- Upload zone: border color shift + subtle scale on drag-hover.
- Processing waveform: continuous idle pulse, splits into four at the relevant stage.
- Card hover: lift (4–6px) + soft amber glow shadow + scale(1.02), 150–200ms snappy easing.
- Buttons: magnetic cursor-follow shift on hover + fill-from-center-out on click.
- Tab switching: sliding underline + text crossfade, never an abrupt cut.
- Confidence count-up animation on results reveal.
- Scroll/reveal transitions: staggered fade + 8px rise, 60–80ms offset between sibling elements.
- Icon micro-animations on "how it works"/differentiator elements (subtle draw-in or idle motion).
- Soft cursor-follow amber glow within the hero/upload section.
- Respect `prefers-reduced-motion` throughout; animate via CSS transform/opacity only for 60fps.

### Icons
Phosphor Icons or Lucide, bold/regular weight only (not thin — washes out on dark backgrounds), consistent stroke width. **Zero emoji anywhere** — UI, labels, or generated caption text.

### Copy Tone
Plain, functional, instructional where needed. No marketing fluff ("revolutionize," "supercharge"). No pricing, no payment language, no sign-up forms — this is a free competition demo end to end.

### Technical
Fully responsive (desktop/tablet/mobile), WCAG AA contrast verified (Warm Bone on Carbon Ink for body text), connects directly to the corrected Fireworks-routed backend pipeline via real API calls — never simulated.

---

## 5. Differentiation Summary (for README / project description / demo)

State clearly in your submission materials:

> "Unlike template-based four-style generators, this agent (1) grounds facts once via an audio-first/vision-fallback branch that correctly handles dialogue, music, silent, and static-image content without hallucination, (2) self-critiques its own captions against the source facts before finalizing, (3) flags which of the four tones is the most natural fit for each specific clip with reasoning, and (4) reports its own per-clip confidence — showing genuine content understanding rather than four independent guesses. Model selection is deliberate: Gemma performs factual visual grounding, while a separate model handles expressive style rewriting — each doing what it's strongest at."

---

## 6. README Requirements

Must include exact run instructions plus a "Design Decisions" section covering:
1. Why audio-first/vision-fallback branching was chosen and how the informativeness threshold works.
2. How music-video and static-image-with-music edge cases are handled naturally by the vision-fallback path with no special-casing.
3. Why Gemma was chosen for grounding vs. a separate model for style rewriting.
4. What the confidence score represents and how it's calculated.
5. Confirmation that all inference is routed through Fireworks AI (`FIREWORKS_BASE_URL`) — no other providers used anywhere in the submitted system.

---

## 7. Pre-Submission Verification Checklist

- [ ] `docker build` succeeds locally with no errors.
- [ ] `docker run` against real sample videos produces valid `results.json` with genuinely distinct, non-fabricated captions per style.
- [ ] `docker pull` of your own pushed public image succeeds from a clean environment (rules out `PULL_ERROR`).
- [ ] Uploading a real video through the web UI returns captions generated from actual transcription/frame analysis — not filename-based guessing.
- [ ] Zero references to `@google/genai`, `GEMINI_API_KEY`, or any non-Fireworks provider remain anywhere in the codebase.
- [ ] Tested on 5+ varied sample clips (dialogue, music, silent, static-image, ambiguous) — both pipeline branches trigger correctly.
- [ ] No pricing/payment language anywhere in the UI.
- [ ] No emoji anywhere in UI or generated captions.
- [ ] README complete with run instructions + Design Decisions section.
- [ ] Confirm exact current Fireworks model IDs (Whisper v3 Turbo, Gemma vision variant, style-generation model) against Fireworks' live catalog before final build — catalogs change, do not hardcode assumed IDs.

---

*End of superprompt. Paste Sections 1–4 directly into Cursor/Antigravity as the build instruction; use Sections 5–7 for your submission writeup and final QA pass.*
