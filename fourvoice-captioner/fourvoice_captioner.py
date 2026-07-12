#!/usr/bin/env python3
"""
FourVoice Captioner - AMD Developer Hackathon ACT II, Track 2 (Video Captioning)
Fully autonomous containerized Python pipeline.

Modes:
  - Batch CLI (default): python fourvoice_captioner.py --input-dir ./input --output ./output/results.json
  - Folder mode:         python fourvoice_captioner.py --input-dir ./videos --output ./output/results.json
"""

import os
import sys
import re
import json
import logging
import argparse
import subprocess
import tempfile
import base64
import time
from collections import Counter
import requests

# Set up logging with a professional console formatter
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("FourVoiceCaptioner")

# Retrieve core environmental variables
FIREWORKS_BASE_URL = os.getenv("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1")
WHISPER_BASE_URL = os.getenv("WHISPER_BASE_URL", "https://audio-prod.api.fireworks.ai/v1")
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY")

# Model IDs — override via env
# Kimi K2 (kimi-k2p6): confirmed serverless VLM on this Fireworks key.
# Whisper v3: runs on dedicated audio endpoints (audio-prod.api.fireworks.ai), not the standard model catalog.
# DeepSeek V4 Pro: used for text-only stages (grounding, style, judging) — clean output, no CoT pollution.
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-v3")
VISION_MODEL = os.getenv("VISION_MODEL", "accounts/fireworks/models/kimi-k2p6")
GROUNDING_TEXT_MODEL = os.getenv("GROUNDING_TEXT_MODEL", "accounts/fireworks/models/deepseek-v4-pro")
STYLE_TEXT_MODEL = os.getenv("STYLE_TEXT_MODEL", "accounts/fireworks/models/deepseek-v4-pro")
JUDGE_TEXT_MODEL = os.getenv("JUDGE_TEXT_MODEL", "accounts/fireworks/models/deepseek-v4-pro")

STYLE_KEYS = ("formal", "sarcastic", "humorous_tech", "humorous_non_tech")
VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".mkv", ".webm", ".MP4", ".MOV", ".MKV", ".WEBM")

def _default_input_dir():
    return "/input" if os.path.isdir("/input") else "./input"


def _default_output_path():
    return "/output/results.json" if os.path.isdir("/output") else "./output/results.json"


INPUT_PATH = os.getenv("INPUT_PATH", "/input/tasks.json" if os.path.isfile("/input/tasks.json") else "./input/tasks.json")
INPUT_DIR = os.getenv("INPUT_DIR", _default_input_dir())
OUTPUT_PATH = os.getenv("OUTPUT_PATH", _default_output_path())
OUTPUT_DIR = os.getenv("OUTPUT_DIR", os.path.dirname(_default_output_path()) or "./output")

# Patterns that indicate leaked model reasoning/metrics/errors, not real captions
INVALID_CAPTION_PATTERNS = [
    re.compile(r"tokens?\s*/\s*sec\.?", re.I),
    re.compile(r"~\s*[\d,]+\s*tokens?", re.I),
    re.compile(r"\b\d+\s*tokens?\s*per", re.I),
    re.compile(r"\bthroughput\b", re.I),
    re.compile(r"\blatency\b", re.I),
    re.compile(r"\bmax_tokens\b", re.I),
    re.compile(r"\bresponse_format\b", re.I),
    re.compile(r"\bfactual_accuracy\b", re.I),
    re.compile(r"\btone_accuracy\b", re.I),
    # Catch leaked HTTP/API error strings
    re.compile(r"^\d{3}:", re.I),  # e.g. "404: ..." or "401: ..."
    re.compile(r"\b(?:exit code|traceback|exception|stack trace)\b", re.I),
    re.compile(r"\brefactored back to\b", re.I),
    re.compile(r"\bgeneric description array\b", re.I),
    re.compile(r"^[\d.]+$"),
    re.compile(r"^[\W\d\s]+$"),
]

def check_dependencies():
    """Ensure ffmpeg is installed and API keys are available."""
    masked_key = (
        f"{FIREWORKS_API_KEY[:8]}...{FIREWORKS_API_KEY[-4:]} ({len(FIREWORKS_API_KEY)} chars)"
        if FIREWORKS_API_KEY
        else "NOT SET"
    )
    logger.info(f"FIREWORKS_API_KEY: {masked_key}")
    logger.info(f"FIREWORKS_BASE_URL: {FIREWORKS_BASE_URL}")
    logger.info(f"WHISPER_BASE_URL:   {WHISPER_BASE_URL}")
    logger.info(f"Whisper Model:       {WHISPER_MODEL}")
    logger.info(f"Vision Model:        {VISION_MODEL}")
    logger.info(f"Grounding Model:     {GROUNDING_TEXT_MODEL}")
    logger.info(f"Style Model:         {STYLE_TEXT_MODEL}")
    logger.info(f"Judge Model:         {JUDGE_TEXT_MODEL}")

    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        logger.info("ffmpeg: OK")
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("ffmpeg is not installed or available in PATH. Please verify your system setup.")
        sys.exit(1)

    if not FIREWORKS_API_KEY:
        logger.error("FIREWORKS_API_KEY environment variable is not set. Exiting.")
        sys.exit(1)


def extract_message_content(res_json):
    """Return only the final assistant caption/content — never reasoning side-channels."""
    choice = res_json.get("choices", [{}])[0]
    message = choice.get("message", {})
    content = message.get("content")

    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(part.get("text", ""))
        content = "\n".join(parts)

    if content is None:
        content = ""
    content = str(content).strip()

    # Some models expose chain-of-thought separately; never treat it as the caption.
    if not content:
        for key in ("reasoning_content", "reasoning", "thinking"):
            alt = message.get(key)
            if alt:
                logger.warning(f"Ignoring non-content field '{key}' in model response")

    return content


def is_valid_caption(text, max_words=40):
    """Reject metrics, JSON blobs, prompt echoes, and other non-caption leakage."""
    if not text or not str(text).strip():
        return False
    candidate = str(text).strip()
    if len(candidate) < 8:
        return False
    if any(p.search(candidate) for p in INVALID_CAPTION_PATTERNS):
        return False
    lower = candidate.lower()
    if lower.startswith("{") or lower.startswith("["):
        return False
    prompt_markers = [
        "write only",
        "output only the caption",
        "factual description:",
        "critical:",
        "your entire response must be",
    ]
    if any(m in lower for m in prompt_markers):
        return False
    if len(candidate.split()) > max_words:
        return False
    return True


def fireworks_chat_completion(model, messages, temperature=0.7, max_tokens=1024, json_mode=False):
    """Call Fireworks Chat Completion API."""
    headers = {
        "Authorization": f"Bearer {FIREWORKS_API_KEY}",
        "Content-Type": "application/json",
    }
    url = f"{FIREWORKS_BASE_URL}/chat/completions"

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    response = requests.post(url, json=payload, headers=headers, timeout=180)
    response.raise_for_status()
    res_json = response.json()
    return extract_message_content(res_json)

def clean_caption_output(raw_text, max_words=40):
    """Extract a short caption from model output; reject reasoning/metric leakage."""
    if not raw_text:
        return ""
    text = str(raw_text).strip()

    # Strategy 0 (highest priority): Look for our explicit CAPTION: ... format
    # The prompt instructs the model to end with CAPTION: "your caption here"
    # Must check BEFORE the "already clean" shortcut since the entire response
    # might be just 'CAPTION: "..."' which would pass is_valid_caption with prefix.
    caption_line_re = re.compile(r'^CAPTION:\s*(.+?)\s*$', re.MULTILINE)
    m = caption_line_re.search(text)
    if m:
        candidate = m.group(1).strip()
        # Strip outer quotes if present (but preserve inner quotes)
        if len(candidate) >= 2 and candidate[0] in '"\u201c' and candidate[-1] in '"\u201d':
            candidate = candidate[1:-1].strip()
        if is_valid_caption(candidate, max_words=max_words):
            return candidate

    # If the entire response is already a clean caption, return it
    if is_valid_caption(text, max_words=max_words):
        return text.strip('"').strip()

    # Strategy 1: Look for explicit caption labels like "Possible caption: ..." or "Caption: ..."
    # DeepSeek V4 Pro often structures reasoning with these markers
    caption_label_re = re.compile(
        r'(?:possible caption|another|caption|option|result|output|answer)[:\s]*["\u201c](.{10,200}?)["\u201d]',
        re.IGNORECASE
    )
    labeled_matches = caption_label_re.findall(text)
    for candidate in labeled_matches:
        cleaned = candidate.strip().strip("'").strip('"').strip()
        if is_valid_caption(cleaned, max_words=max_words):
            return cleaned

    # Strategy 2: Try all quoted spans (both straight and curly quotes)
    # Use a broader pattern that handles escaped quotes
    quoted = re.findall(r'["\u201c]([^"\u201d]{10,200})["\u201d]', text)
    for candidate in reversed(quoted):
        candidate = candidate.strip()
        # Skip candidates that look like reasoning/meta-text
        lower = candidate.lower()
        if any(lower.startswith(p) for p in ("write a", "we are", "the factual", "base this")):
            continue
        if is_valid_caption(candidate, max_words=max_words):
            return candidate

    # Strategy 3: Try last non-reasoning line
    lines = [ln.strip().strip('"') for ln in text.split("\n") if ln.strip()]
    reasoning_prefixes = (
        "we ", "i ", "the user", "let me", "so ", "another", "maybe", "perhaps",
        "but ", "however", "the instruction", "the description", "the clip",
        "note:", "thinking:", "analysis:", "here is", "here's", "caption:",
        "output:", "response:", "answer:", "possible caption:", "count",
        "word count:", "that's ", "that is ", "check:",
        "- ", "* ",  # bullet points are reasoning fragments, not captions
    )
    numbered_re = re.compile(r'^\d+[\.)\]]\s')
    for line in reversed(lines):
        lower = line.lower()
        if any(lower.startswith(p) for p in reasoning_prefixes):
            continue
        if numbered_re.match(line):
            continue
        if line.count("**") >= 2:
            continue
        if is_valid_caption(line, max_words=max_words):
            return line

    return ""

def transcribe_audio_whisper(audio_path):
    """Transcribe audio via Fireworks Whisper STT."""
    if not os.path.exists(audio_path) or os.path.getsize(audio_path) < 100:
        logger.warning("Audio file missing or too small; returning empty transcript.")
        return ""

    headers = {"Authorization": f"Bearer {FIREWORKS_API_KEY}"}
    url = f"{WHISPER_BASE_URL}/audio/transcriptions"
    try:
        with open(audio_path, "rb") as f:
            files = {"file": (os.path.basename(audio_path), f, "audio/mpeg")}
            data = {"model": WHISPER_MODEL, "response_format": "json", "language": "en"}
            logger.info(f"Whisper request: POST {url} model={WHISPER_MODEL} file_size={os.path.getsize(audio_path)} bytes")
            response = requests.post(url, files=files, data=data, headers=headers, timeout=300)
            logger.info(f"Whisper response: HTTP {response.status_code}")
            if response.status_code != 200:
                logger.error(f"Whisper HTTP {response.status_code}: {response.text[:500]}")
                return ""
            response.raise_for_status()
            payload = response.json()
            text = payload.get("text", "") if isinstance(payload, dict) else str(payload)
            logger.info(f"Whisper raw output ({len(text)} chars): {text[:200]!r}")
            return (text or "").strip()
    except requests.exceptions.HTTPError as e:
        logger.error(f"Whisper STT failed: HTTP {e.response.status_code if e.response else '?'} — {e}")
        return ""
    except Exception as e:
        logger.error(f"Whisper STT transcription failed: {e}")
        return ""


def tokenize_words(text):
    """Count real spoken words, excluding timestamps/metadata tokens."""
    return re.findall(r"[A-Za-z]+(?:['\u2019][A-Za-z]+)?", text)


def calculate_word_diversity(text):
    """Ratio of unique words to total words."""
    words = [w.lower() for w in tokenize_words(text)]
    if not words:
        return 0.0
    return len(set(words)) / len(words)


def assess_audio_informativeness(transcript):
    """
    General heuristic: >15 real words, diversity >= 0.45, no single word dominates.
    Returns (is_informative, metrics_dict).
    """
    words = tokenize_words(transcript)
    word_count = len(words)
    diversity = calculate_word_diversity(transcript)
    max_word_freq = 0.0
    if words:
        counts = Counter(w.lower() for w in words)
        max_word_freq = counts.most_common(1)[0][1] / word_count

    is_informative = (
        word_count > 15
        and diversity >= 0.45
        and max_word_freq < 0.25
    )
    metrics = {
        "word_count": word_count,
        "diversity": round(diversity, 3),
        "max_word_freq_ratio": round(max_word_freq, 3),
        "branch": "3A_audio" if is_informative else "3B_vision",
    }
    return is_informative, metrics

def extract_audio(video_path, temp_dir):
    """Extract audio track from video using ffmpeg."""
    audio_output = os.path.join(temp_dir, "extracted_audio.mp3")
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-acodec", "libmp3lame", "-ar", "16000", "-ac", "1",
        audio_output
    ]
    logger.info(f"Extracting audio to {audio_output}...")
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return audio_output

def generate_thumbnail(video_path, output_path):
    """Generate a thumbnail image from the video at the 1-second mark."""
    cmd = [
        "ffmpeg", "-y", "-ss", "1", "-i", video_path,
        "-vframes", "1", "-q:v", "2", "-vf", "scale=320:-1", output_path
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        if os.path.exists(output_path):
            return output_path
    except Exception as e:
        logger.warning(f"Thumbnail generation failed: {e}")
    return None

def probe_duration(video_path):
    """Return video duration in seconds via ffprobe."""
    duration_cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", video_path,
    ]
    try:
        res = subprocess.run(duration_cmd, capture_output=True, text=True, check=True)
        return float(res.stdout.strip())
    except Exception as e:
        logger.warning(f"Failed to probe duration, defaulting to 10s: {e}")
        return 10.0


def extract_frames(video_path, temp_dir, num_frames=9, max_side=512, bias_late=True):
    """Extract frames with late-clip bias for action-aware analysis.

    Returns (frame_paths, timestamps) where timestamps are in seconds.
    When bias_late=True, samples 6 evenly-spaced frames across the full
    duration plus 3 extra frames concentrated in the last 30% of the clip
    to capture the final state / payoff moment.
    """
    duration = probe_duration(video_path)
    timestamps = []

    if bias_late and num_frames >= 9:
        # 6 evenly spaced across full duration
        n_even = num_frames - 3
        even_interval = duration / (n_even + 1)
        for i in range(1, n_even + 1):
            timestamps.append(round(i * even_interval, 2))
        # 3 extra in the last 30% of the clip
        late_start = duration * 0.70
        late_interval = (duration - late_start) / 4
        for i in range(1, 4):
            t = round(late_start + i * late_interval, 2)
            if t not in timestamps and t < duration:
                timestamps.append(t)
        timestamps.sort()
    else:
        interval = duration / (num_frames + 1)
        for i in range(1, num_frames + 1):
            timestamps.append(round(i * interval, 2))

    frame_paths = []
    for idx, ts in enumerate(timestamps):
        frame_name = f"frame_{idx + 1:02d}.jpg"
        frame_path = os.path.join(temp_dir, frame_name)
        cmd = [
            "ffmpeg", "-y", "-ss", str(ts), "-i", video_path,
            "-vframes", "1", "-vf", f"scale='min({max_side},iw)':-1",
            "-q:v", "4", frame_path,
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        if os.path.exists(frame_path):
            frame_paths.append(frame_path)

    logger.info(f"Extracted {len(frame_paths)} frames (duration={duration:.1f}s, bias_late={bias_late}) for multimodal analysis.")
    return frame_paths, timestamps

def load_reference_captions():
    """Load reference captions for keyword-overlap grounding."""
    ref_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reference_captions.json")
    try:
        with open(ref_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Could not load reference_captions.json: {e}")
        return []


def select_reference_examples(factual_description, reference_captions, top_k=4):
    """Simple keyword-overlap matching to find the most relevant reference captions."""
    if not reference_captions or not factual_description:
        return reference_captions[:top_k] if reference_captions else []

    desc_words = set(w.lower() for w in re.findall(r'[A-Za-z]+', factual_description) if len(w) > 2)
    scored = []
    for caption in reference_captions:
        cap_words = set(w.lower() for w in re.findall(r'[A-Za-z]+', caption) if len(w) > 2)
        overlap = len(desc_words & cap_words)
        scored.append((overlap, caption))
    scored.sort(key=lambda x: -x[0])
    return [cap for _, cap in scored[:top_k]]


def analyze_frames_vision(frame_paths, timestamps=None, partial_transcript="", num_frames=9):
    """Vision-grounded factual description using VLM with action-aware prompt."""
    model = VISION_MODEL
    parts = []

    # Load reference examples for the grounding prompt
    ref_captions = load_reference_captions()
    example_block = ""
    if ref_captions:
        examples = ref_captions[:5]
        example_block = (
            "\n\nHere are examples of the level of specificity and concreteness expected:\n"
            + "\n".join(f"- {ex}" for ex in examples)
            + "\n\nMatch this level of specificity and concreteness — avoid vague phrasing like "
            "'features visual elements' or 'accompanying sound'."
        )

    # Build timestamp label string
    ts_labels = ""
    if timestamps and len(timestamps) == len(frame_paths):
        ts_labels = (
            "The frames are labeled with timestamps below. Use them to understand temporal order.\n"
        )

    text_content = (
        "You are describing a video clip for someone who cannot see it. "
        "These frames are sampled across the full duration of the clip (timestamps shown).\n"
        f"{ts_labels}"
        "Analyze the frames IN ORDER and describe:\n"
        "1. TIMELINE: What changes or progresses from the first frame to the last? "
        "Note what appears early vs. what appears later.\n"
        "2. MAIN ACTION: What is the single most important thing that HAPPENS in this clip? "
        "Focus on the action the clip is demonstrating or accomplishing.\n"
        "3. FINAL STATE: What is the end result or payoff shown in the later frames? "
        "This is usually the most important detail to get right.\n"
        "4. DETAILS: Any on-screen text, values, names, labels — note WHICH part of the "
        "timeline they appear in (early, middle, or late). If the same type of item appears "
        "multiple times (e.g., two different names/keys/values), clearly distinguish which is "
        "pre-existing vs. newly created.\n"
        "5. STYLE: Is it live-action, animated, screen recording, illustrated, etc.?\n\n"
        "Write 3-5 sentences focusing on what the clip ACCOMPLISHES, not just what is visible. "
        "Prioritize the completed action and final state over incidental early-frame details. "
        "Do not guess what you cannot see."
    )
    if partial_transcript:
        text_content += f'\nAudio transcript for context: "{partial_transcript[:500]}"'
    text_content += example_block

    parts.append({"type": "text", "text": text_content})

    # Select frames — use all if within limits
    if len(frame_paths) > num_frames:
        step = max(1, len(frame_paths) // num_frames)
        indices = list(range(0, len(frame_paths), step))[:num_frames]
    else:
        indices = list(range(len(frame_paths)))

    for idx in indices:
        path = frame_paths[idx]
        # Add timestamp label before each frame
        if timestamps and idx < len(timestamps):
            ts_sec = timestamps[idx]
            mins, secs = divmod(int(ts_sec), 60)
            parts.append({"type": "text", "text": f"Frame {idx + 1} ({mins}:{secs:02d})"})
        with open(path, "rb") as image_file:
            base64_data = base64.b64encode(image_file.read()).decode("utf-8")
            parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{base64_data}"},
            })

    messages = [{"role": "user", "content": parts}]
    logger.info(f"Calling vision model ({model}) with {len(indices)} frames...")
    raw = fireworks_chat_completion(model, messages, temperature=0.2, max_tokens=1000)
    return strip_vision_cot(raw)


def _bullets_to_prose(text):
    """Convert a block containing bullet points into flowing prose."""
    lines = text.split("\n")
    result_parts = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Strip bullet markers
        cleaned = re.sub(r'^[-*]\s+', '', stripped)
        # Strip trailing header colons from lines like "All the frames show:"
        if cleaned.endswith(":") and len(cleaned.split()) < 8:
            cleaned = cleaned[:-1]  # Remove trailing colon from header-like lines
            if cleaned:
                result_parts.append(cleaned + ":")
        else:
            result_parts.append(cleaned)
    return " ".join(result_parts)



def _strip_description_prefix(text):
    """Strip common model-generated prefixes from descriptions.

    Models sometimes prefix their descriptions with phrases like 'Draft:', 'Here is
    the description:', etc. This strips those prefixes while preserving the content.
    """
    if not text:
        return text
    # Patterns to strip (case-insensitive)
    prefix_patterns = [
        r'^Draft:\s*',
        r'^Here (?:is|are) (?:the |my |a )?(?:description|response|answer)s?[:\s]*',
        r'^(?:Final |Updated )?Description:\s*',
        r'^(?:My |The )?(?:response|answer):\s*',
    ]
    result = text
    for pattern in prefix_patterns:
        result = re.sub(pattern, '', result, flags=re.IGNORECASE).strip()
    return result


def strip_vision_cot(text):
    """Strip chain-of-thought reasoning from vision model output.

    Models like kimi-k2p6 prefix their response with reasoning like:
      'The user wants me to describe... Let me look at the frames...\n\n[actual description]'
    This extracts only the factual description portion.
    """
    if not text:
        return text

    # Check if the response starts with reasoning indicators
    reasoning_starters = (
        "the user want", "let me", "i need to", "i should", "looking at",
        "i'll describe", "i will describe", "ok, let me", "okay",
        "wait", "hmm", "so,", "alright", "first", "now,",
    )
    lower = text.lower().lstrip()
    if not any(lower.startswith(s) for s in reasoning_starters):
        # No CoT detected — but still strip common prefixes like "Draft:"
        text = _strip_description_prefix(text)
        return text

    logger.info(f"Vision CoT detected ({len(text)} chars), extracting description...")

    # Strategy 1: Find content after a double-newline separator that looks like the actual answer
    # Models typically reason in the first block, then write the answer after a blank line
    blocks = re.split(r'\n\s*\n', text)
    if len(blocks) >= 2:
        # Score blocks: prefer prose blocks over bullet-list blocks
        best_block = None
        best_score = -1
        for i, block in enumerate(blocks):
            block_stripped = block.strip()
            block_lower = block_stripped.lower()
            # Skip blocks that are clearly reasoning
            if any(block_lower.startswith(s) for s in reasoning_starters):
                continue
            if block_lower.startswith("frame ") or block_lower.startswith("- frame"):
                continue
            if len(block_stripped) < 30:
                continue

            # Score: prose blocks get higher scores than bullet blocks
            score = len(block_stripped)
            bullet_lines = sum(1 for ln in block_stripped.split("\n") if ln.strip().startswith("- "))
            total_lines = len([ln for ln in block_stripped.split("\n") if ln.strip()])
            if bullet_lines > 0:
                score = score * 0.5  # Penalize bullet blocks
            if re.match(r'^\d+\.', block_stripped):
                score = score * 0.3  # Penalize numbered lists

            if score > best_score:
                best_score = score
                best_block = block_stripped

        if best_block:
            # Convert any remaining bullet points to prose
            result = _bullets_to_prose(best_block)
            result = _strip_description_prefix(result)
            logger.info(f"Vision CoT: extracted description ({len(result)} chars)")
            return result

    # Strategy 2: If no clean block found, concatenate all non-reasoning lines into prose
    lines = text.split("\n")
    desc_lines = []
    past_reasoning = False
    for line in lines:
        stripped = line.strip()
        lower_line = stripped.lower()
        if not past_reasoning:
            if any(lower_line.startswith(s) for s in reasoning_starters):
                continue
            if stripped == "" and not desc_lines:
                past_reasoning = True
                continue
        if stripped and not stripped.startswith("- Frame") and not lower_line.startswith("let me"):
            # Strip bullet markers
            cleaned = re.sub(r'^[-*]\s+', '', stripped)
            if cleaned:
                desc_lines.append(cleaned)

    if desc_lines:
        result = " ".join(desc_lines)
        result = _strip_description_prefix(result)
        logger.info(f"Vision CoT: reconstructed {len(result)} chars from {len(desc_lines)} lines")
        return result

    # Fallback: return the raw text
    logger.warning("Vision CoT: could not extract clean description, using raw output")
    return text

STYLE_PROMPTS = {
    "formal": (
        "Write a single neutral, professional, factual caption describing this clip in 1-2 sentences. "
        "Third person, no opinion, no humor, no personality. "
        "It should read like a technical log entry or press release — precise and detached."
    ),
    "sarcastic": (
        "Write a single dry, sarcastic caption reacting to this clip, under 25 words. "
        "Sound like a bored commentator or deadpan news anchor — understated, not loud. "
        "Use ironic understatement or exaggerated gravitas. Do NOT make jokes — just state "
        "the obvious with weary detachment. Must stay clearly connected to the actual clip content."
    ),
    "humorous_tech": (
        "Write a single funny caption using tech/developer culture humor, under 25 words. "
        "The humor MUST require understanding the technical context to land — reference specific "
        "tools, workflows, jargon, or dev-culture tropes visible in the clip. "
        "The caption MUST contain a real joke, wordplay, or comedic observation tied to a specific detail "
        "from the factual description — not a generic or hedge-like statement.\n"
        'Example: For a video of someone assembling furniture: '
        '"This IKEA build has more dependencies than my node_modules folder and the instructions are about as clear as regex."'
    ),
    "humorous_non_tech": (
        "Write a single funny, broadly relatable caption with everyday humor, under 25 words. "
        "Reframe the observation for someone with ZERO tech background — use everyday analogies "
        "(cooking, sports, daily life, family). Absolutely no jargon or tech terms. "
        "The caption MUST contain a real joke, wordplay, or comedic observation tied to a specific detail "
        "from the factual description — not a generic or hedge-like statement.\n"
        'Example: For a video of a toddler stacking blocks: '
        '"Future architect, current demolition expert. The joy on that face when the tower falls is deeply concerning."'
    ),
}


# Safe fallback captions that are honest about failure — never error strings
SAFE_FALLBACKS = {
    "formal": "A short video clip. Caption could not be generated at this time.",
    "sarcastic": "Caption generation tried its best. It wasn't enough.",
    "humorous_tech": "Humor module threw an unhandled exception. Stack trace: just vibes.",
    "humorous_non_tech": "The caption machine called in sick today.",
}


def generate_style_caption(style, factual_description, temperature=0.8):
    """Stage 4: one style caption from grounded description only."""
    max_words = 60 if style == "formal" else 30

    # Build user content with reference examples for specificity
    ref_captions = load_reference_captions()
    ref_examples = select_reference_examples(factual_description, ref_captions, top_k=4)
    ref_block = ""
    if ref_examples and style in ("formal",):
        ref_block = (
            "\n\nReference examples for specificity level:\n"
            + "\n".join(f"- {ex}" for ex in ref_examples)
            + "\nMatch this level of concreteness."
        )

    system_instruction = (
        f"{STYLE_PROMPTS[style]}\n"
        "Base this only on the factual description provided. Do not introduce any fact, detail, or claim not present in that description.\n"
        "You may think through your approach, but your FINAL line must be exactly:\n"
        'CAPTION: "your caption here"\n'
        "Nothing may follow the CAPTION line."
    )
    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": f"Factual Description:\n{factual_description}{ref_block}"},
    ]
    # deepseek-v4-pro embeds reasoning in content (~1000 tokens) before the caption;
    # 300 max_tokens was truncating the output before it could write the actual answer.
    raw_output = fireworks_chat_completion(STYLE_TEXT_MODEL, messages, temperature=temperature, max_tokens=2048)
    logger.info(f"STAGE 4 RAW '{style}' ({len(raw_output)} chars): {raw_output[:300]!r}")
    cleaned = clean_caption_output(raw_output, max_words=max_words).strip().strip('"')
    if is_valid_caption(cleaned, max_words=max_words):
        return cleaned
    logger.warning(f"Invalid caption output for '{style}' (raw={raw_output[:80]!r}, cleaned={cleaned[:80]!r}); using safe fallback")
    return SAFE_FALLBACKS.get(style, "Caption unavailable.")


def run_self_qc(factual_description, captions):
    """
    Stage 5: single batched QC call for all four captions.
    Returns dict[style] -> {factual_accuracy, tone_accuracy}; regenerates at most once per failing style.
    """
    qc_payload = {
        style: captions[style] for style in STYLE_KEYS if style in captions
    }
    qc_prompt = (
        "You are an internal quality control judge. For each caption below, score factual accuracy "
        "against the source description (1-5) and tone match to its intended style (1-5).\n"
        'Return JSON: {"scores": {"formal": {"factual_accuracy": 4, "tone_accuracy": 5}, ...}}'
    )
    messages = [
        {"role": "system", "content": qc_prompt},
        {
            "role": "user",
            "content": f"Factual source description:\n{factual_description}\n\nCaptions:\n{json.dumps(qc_payload, indent=2)}",
        },
    ]
    raw = fireworks_chat_completion(JUDGE_TEXT_MODEL, messages, temperature=0.1, max_tokens=600, json_mode=True)
    try:
        parsed = json.loads(raw)
        scores = parsed.get("scores", parsed)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", raw)
        scores = json.loads(match.group()).get("scores", {}) if match else {}

    regenerated = []
    for style in STYLE_KEYS:
        style_scores = scores.get(style, {})
        fact_score = style_scores.get("factual_accuracy", 4)
        tone_score = style_scores.get("tone_accuracy", 4)
        logger.info(f"STAGE 5: QC '{style}' -> fact={fact_score}/5 tone={tone_score}/5")
        if fact_score < 3 or tone_score < 3:
            logger.warning(f"STAGE 5: Regenerating '{style}' (one retry max)")
            retry = generate_style_caption(style, factual_description, captions[style], temperature=0.7)
            if is_valid_caption(retry, max_words=40 if style == "formal" else 25):
                captions[style] = retry
                regenerated.append(style)
    if regenerated:
        logger.info(f"STAGE 5: Regenerated styles: {regenerated}")
    return captions, scores


def verify_grounding_and_captions(factual_description, captions, frame_paths, timestamps=None):
    """Merged verification: check grounding facts AND caption fact consistency.

    Uses the text model (not VLM) for reliable JSON output. The factual description
    already captures what was seen in the frames, so we verify internal consistency
    and caption fidelity against that shared grounding.
    Only flags specific named details (names, numbers, values) — not general descriptions.
    """
    if not factual_description or not captions:
        logger.warning("VERIFY: Missing description or captions, skipping")
        return None

    caption_block = "\n".join(f"  {k}: {v}" for k, v in captions.items())

    verify_prompt = (
        "You are a fact-checker for video captions. You will receive a factual description of a video "
        "clip and 4 style captions derived from it.\n\n"
        "Tasks:\n"
        "1. EXTRACT FACTS: List every specific, named fact in the factual description "
        "(names, numbers, values, labels, UI elements, actions).\n"
        "2. VERIFY CAPTIONS: For each of the 4 captions, check if it introduces any specific fact "
        "(a name, number, value, filename, label) that is NOT present in the factual description.\n"
        "3. ASSESS CONFIDENCE: Are the facts in the description internally consistent and specific "
        "enough to support the captions?\n\n"
        'Return ONLY valid JSON — no reasoning, no markdown, no explanation:\n'
        '{\n'
        '  "confirmed": ["list of specific facts from the description"],\n'
        '  "unconfirmed": ["any facts that seem internally inconsistent or vague"],\n'
        '  "per_caption_issues": {\n'
        '    "formal": ["any ungrounded facts introduced by this caption"],\n'
        '    "sarcastic": [],\n'
        '    "humorous_tech": [],\n'
        '    "humorous_non_tech": []\n'
        '  }\n'
        '}\n\n'
        "IMPORTANT: Only flag SPECIFIC named details (names, numbers, values) as issues. "
        "Do NOT flag general descriptive claims or creative reframings."
    )

    messages = [
        {"role": "system", "content": verify_prompt},
        {"role": "user", "content": (
            f"FACTUAL DESCRIPTION:\n{factual_description}\n\n"
            f"CAPTIONS:\n{caption_block}"
        )},
    ]

    logger.info("VERIFY: Running merged grounding + caption verification...")
    t0 = time.perf_counter()
    raw = fireworks_chat_completion(JUDGE_TEXT_MODEL, messages, temperature=0.1, max_tokens=1200, json_mode=True)
    elapsed = time.perf_counter() - t0
    logger.info(f"VERIFY: Completed in {elapsed:.1f}s")

    # Parse JSON — handle CoT wrapper from deepseek
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON from within reasoning text
        match = re.search(r'\{[\s\S]*"confirmed"[\s\S]*"per_caption_issues"[\s\S]*\}', raw)
        if match:
            try:
                result = json.loads(match.group())
            except json.JSONDecodeError:
                logger.warning(f"VERIFY: Could not parse verification JSON: {raw[:300]}")
                return None
        else:
            logger.warning(f"VERIFY: No JSON in verification response: {raw[:300]}")
            return None

    confirmed = result.get("confirmed", [])
    unconfirmed = result.get("unconfirmed", [])
    per_caption = result.get("per_caption_issues", {})

    logger.info(f"VERIFY: {len(confirmed)} confirmed, {len(unconfirmed)} unconfirmed facts")
    for fact in confirmed:
        logger.info(f"  CONFIRMED: {fact}")
    for fact in unconfirmed:
        logger.warning(f"  UNCONFIRMED: {fact}")
    for style, issues in per_caption.items():
        if issues:
            logger.warning(f"  CAPTION ISSUE [{style}]: {issues}")

    return result


def compute_confidence(is_audio_informative, info_metrics, factual_description,
                       qc_scores, grounding_verification=None):
    """Stage 7: evidence-based confidence reflecting grounding quality.

    Factors:
    - Base: grounding source strength (audio > rich vision > sparse vision)
    - Evidence: ratio of verified-to-total facts from grounding verification
    - Judge: average factual accuracy from QC scores
    - Audio bonus: transcript richness
    """
    word_count = info_metrics.get("word_count", 0)

    # Base: how strong is the grounding source?
    if is_audio_informative:
        base = 0.40
    elif len(factual_description) > 150:
        base = 0.35  # Rich vision description = good grounding
    else:
        base = 0.20  # Sparse description = weak grounding

    # Evidence component: how many facts were verified?
    if grounding_verification:
        confirmed = len(grounding_verification.get("confirmed", []))
        unconfirmed = len(grounding_verification.get("unconfirmed", []))
        total = confirmed + unconfirmed
        evidence_ratio = confirmed / max(total, 1)
        evidence_component = evidence_ratio * 0.30
    else:
        # No verification run — use description richness as proxy
        evidence_component = min(len(factual_description), 400) / 400.0 * 0.25

    # Judge component (QC scores)
    judge_scores = []
    for style in STYLE_KEYS:
        style_scores = qc_scores.get(style, {}) if isinstance(qc_scores, dict) else {}
        fact = style_scores.get("factual_accuracy", 3)
        try:
            judge_scores.append(float(fact) / 5.0)
        except (TypeError, ValueError):
            judge_scores.append(0.6)
    judge_component = (sum(judge_scores) / len(judge_scores) if judge_scores else 0.6) * 0.25

    # Audio bonus
    audio_component = min(word_count, 50) / 50.0 * 0.10 if is_audio_informative else 0.0

    confidence = base + evidence_component + judge_component + audio_component
    return round(max(0.0, min(1.0, confidence)), 2)


def load_tasks():
    """Normalize input into a list of task dicts with task_id, styles, and video source."""
    # Hackathon tasks.json mode
    if os.path.isfile(INPUT_PATH):
        with open(INPUT_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        tasks = []
        for item in raw:
            tasks.append({
                "task_id": item["task_id"],
                "video_url": item["video_url"],
                "styles": item.get("styles", list(STYLE_KEYS)),
            })
        logger.info(f"Loaded {len(tasks)} tasks from {INPUT_PATH} (hackathon mode).")
        return "tasks_json", tasks

    # Folder mode (Docker harness batch scoring)
    if os.path.isdir(INPUT_DIR) and find_videos_in_dir(INPUT_DIR):
        tasks = []
        for video_path in find_videos_in_dir(INPUT_DIR):
            stem = os.path.splitext(os.path.basename(video_path))[0]
            tasks.append({
                "task_id": stem,
                "video_path": video_path,
                "styles": list(STYLE_KEYS),
            })
        logger.info(f"Loaded {len(tasks)} videos from {INPUT_DIR} (folder mode).")
        return "folder", tasks

    logger.warning("No tasks.json or video files found in input paths.")
    return None, []


def generate_thumbnail(video_path, output_path):
    """Generate a thumbnail image from the video at the 1-second mark."""
    cmd = [
        "ffmpeg", "-y", "-ss", "1", "-i", video_path,
        "-vframes", "1", "-q:v", "2", "-vf", "scale=320:-1", output_path
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        if os.path.exists(output_path):
            return output_path
    except Exception as e:
        logger.warning(f"Thumbnail generation failed: {e}")
    return None


def find_videos_in_dir(directory):
    """Return sorted unique video paths under a directory."""
    videos = []
    for name in os.listdir(directory):
        if any(name.endswith(ext) for ext in VIDEO_EXTENSIONS):
            videos.append(os.path.join(directory, name))
    return sorted(set(videos))


def fallback_task_result(task_id, video_name=None):
    """Safe per-task output when processing fails — never leak internal errors as captions."""
    return {
        "video": video_name or task_id,
        "formal": SAFE_FALLBACKS["formal"],
        "sarcastic": SAFE_FALLBACKS["sarcastic"],
        "humorous_tech": SAFE_FALLBACKS["humorous_tech"],
        "humorous_non_tech": SAFE_FALLBACKS["humorous_non_tech"],
        "recommended_style": "formal",
        "reasoning": "Neutral tone is safest when clip context is ambiguous.",
        "confidence": 0.10,
        "task_id": task_id,
    }


def write_results(results, output_path):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)


def write_folder_per_video_outputs(results, output_dir):
    """Folder mode: also emit one JSON file per clip."""
    os.makedirs(output_dir, exist_ok=True)
    for item in results:
        video_name = item.get("video", "clip")
        stem = os.path.splitext(video_name)[0]
        per_path = os.path.join(output_dir, f"{stem}.json")
        with open(per_path, "w", encoding="utf-8") as f:
            json.dump(item, f, indent=2)


def process_single_video(video_path):
    """Run full 8-stage video processing pipeline on a single clip."""
    pipeline_start = time.perf_counter()
    timings = {}

    logger.info("=" * 60)
    logger.info(f"PROCESSING VIDEO: {os.path.basename(video_path)}")
    logger.info("=" * 60)

    transcript = ""
    info_metrics = {}
    is_audio_informative = False
    grounding_branch = "3B_vision"
    factual_description = ""

    with tempfile.TemporaryDirectory() as temp_dir:
        # STAGE 1 — Audio transcription
        t0 = time.perf_counter()
        try:
            audio_path = extract_audio(video_path, temp_dir)
            transcript = transcribe_audio_whisper(audio_path)
            logger.info(f"STAGE 1 complete in {time.perf_counter() - t0:.1f}s")
            logger.info(f"STAGE 1 RAW TRANSCRIPT ({len(tokenize_words(transcript))} words):\n{transcript or '(empty)'}")
        except Exception as e:
            logger.error(f"STAGE 1 failed: {e}")
        timings["stage1_transcription_sec"] = round(time.perf_counter() - t0, 2)

        # STAGE 2 — Informativeness branch
        t0 = time.perf_counter()
        is_audio_informative, info_metrics = assess_audio_informativeness(transcript)
        grounding_branch = info_metrics["branch"]
        logger.info(
            f"STAGE 2 ({time.perf_counter() - t0:.2f}s): words={info_metrics['word_count']} "
            f"diversity={info_metrics['diversity']} max_word_freq={info_metrics['max_word_freq_ratio']} "
            f"-> {grounding_branch}"
        )
        timings["stage2_informativeness_sec"] = round(time.perf_counter() - t0, 2)

        # STAGE 3 — Grounded description
        t0 = time.perf_counter()
        frame_paths = []
        frame_timestamps = []
        if is_audio_informative:
            try:
                system_prompt = (
                    "Based on this transcript, write a neutral, factual, detailed description of what is happening "
                    "in this video clip. State only what is directly evidenced by the transcript. "
                    "Do not invent visual details you cannot know from audio alone."
                )
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Transcript:\n{transcript}"},
                ]
                logger.info("STAGE 3A: Audio-grounded description...")
                factual_description = fireworks_chat_completion(
                    GROUNDING_TEXT_MODEL, messages, temperature=0.1, max_tokens=500
                )
            except Exception as e:
                logger.error(f"STAGE 3A failed: {e}. Falling back to vision.")
                is_audio_informative = False
                grounding_branch = "3B_vision"

        if not is_audio_informative or not factual_description.strip():
            try:
                frame_paths, frame_timestamps = extract_frames(video_path, temp_dir, num_frames=9)
                factual_description = analyze_frames_vision(
                    frame_paths, timestamps=frame_timestamps, partial_transcript=transcript
                )
                grounding_branch = "3B_vision"
                logger.info(f"STAGE 3B Vision-Grounded Description: {factual_description[:200]}...")
            except Exception as e:
                logger.error(f"STAGE 3B failed: {e}")
                factual_description = "The clip depicts visual movement and ambient audio."
                if transcript:
                    factual_description += f" Partial audio: {transcript[:300]}"
        else:
            logger.info(f"STAGE 3A Audio-Grounded Description: {factual_description[:200]}...")
            # Still extract frames for verification even with audio grounding
            try:
                frame_paths, frame_timestamps = extract_frames(video_path, temp_dir, num_frames=9)
            except Exception as e:
                logger.warning(f"Frame extraction for verification failed: {e}")

        timings["stage3_grounding_sec"] = round(time.perf_counter() - t0, 2)

        # STAGE 4 — Four style captions
        t0 = time.perf_counter()
        captions = {}
        for style in STYLE_KEYS:
            try:
                logger.info(f"STAGE 4: Generating '{style}'...")
                captions[style] = generate_style_caption(
                    style, factual_description
                )
                logger.info(f"  '{style}': \"{captions[style]}\"")
            except Exception as e:
                logger.error(f"STAGE 4 failed for {style}: {e}")
                captions[style] = SAFE_FALLBACKS.get(style, "Caption unavailable.")
        timings["stage4_captions_sec"] = round(time.perf_counter() - t0, 2)

        # STAGE 4B — Merged grounding + caption verification
        t0 = time.perf_counter()
        grounding_verification = None
        try:
            if frame_paths and len(frame_paths) >= 3:
                grounding_verification = verify_grounding_and_captions(
                    factual_description, captions, frame_paths, timestamps=frame_timestamps
                )
                # Handle per-caption issues: regenerate captions with ungrounded facts
                if grounding_verification:
                    per_caption = grounding_verification.get("per_caption_issues", {})
                    for style, issues in per_caption.items():
                        if issues and style in captions:
                            # Only regenerate if there are specific named-detail issues
                            named_issues = [i for i in issues if any(c.isupper() or c.isdigit() for c in str(i))]
                            if named_issues:
                                logger.warning(f"VERIFY: Regenerating '{style}' due to ungrounded facts: {named_issues}")
                                retry = generate_style_caption(style, factual_description, temperature=0.6)
                                if is_valid_caption(retry, max_words=40 if style == "formal" else 25):
                                    captions[style] = retry
                                    logger.info(f"  '{style}' regenerated: \"{retry}\"")
        except Exception as e:
            logger.error(f"STAGE 4B verification failed: {e}")
        timings["stage4b_verification_sec"] = round(time.perf_counter() - t0, 2)

        # STAGE 5 — Self-QC (single batched call + max 1 regen per style)
        t0 = time.perf_counter()
        qc_scores = {}
        try:
            captions, qc_scores = run_self_qc(factual_description, captions)
        except Exception as e:
            logger.error(f"STAGE 5 QC failed: {e}")
        timings["stage5_qc_sec"] = round(time.perf_counter() - t0, 2)

        # STAGE 6 — Tone recommendation
        t0 = time.perf_counter()
        recommended_style = "formal"
        reasoning = ""
        try:
            rec_prompt = (
                "Given this factual description of the clip, which of these four tones — formal, sarcastic, "
                "humorous_tech, humorous_non_tech — best matches the clip's natural emotional register? "
                'Answer as JSON: {"recommended_style": "sarcastic", "reasoning": "One sentence reason."}'
            )
            messages = [
                {"role": "system", "content": rec_prompt},
                {"role": "user", "content": f"Factual description:\n{factual_description}"},
            ]
            rec_res_raw = fireworks_chat_completion(JUDGE_TEXT_MODEL, messages, temperature=0.2, json_mode=True)
            try:
                rec_res = json.loads(rec_res_raw)
            except json.JSONDecodeError:
                match = re.search(r"\{[^}]*\"recommended_style\"[^}]*\}", rec_res_raw)
                rec_res = json.loads(match.group()) if match else {"recommended_style": "formal", "reasoning": ""}
            recommended_style = rec_res.get("recommended_style", "formal").replace("-", "_")
            reasoning = rec_res.get("reasoning", "")
            logger.info(f"STAGE 6: recommended={recommended_style} | {reasoning}")
        except Exception as e:
            logger.error(f"STAGE 6 failed: {e}")
            reasoning = "Neutral professional assessment is safest for ambiguous contexts."
        timings["stage6_tone_sec"] = round(time.perf_counter() - t0, 2)

        # STAGE 7 — Confidence (now uses verification evidence)
        confidence = compute_confidence(
            is_audio_informative, info_metrics, factual_description, qc_scores,
            grounding_verification=grounding_verification
        )
        logger.info(f"STAGE 7: confidence={confidence}")

        timings["total_sec"] = round(time.perf_counter() - pipeline_start, 2)
        logger.info(f"TIMING BREAKDOWN: {json.dumps(timings)}")

        output_data = {
            "video": os.path.basename(video_path),
            "formal": captions.get("formal", SAFE_FALLBACKS["formal"]),
            "sarcastic": captions.get("sarcastic", SAFE_FALLBACKS["sarcastic"]),
            "humorous_tech": captions.get("humorous_tech", SAFE_FALLBACKS["humorous_tech"]),
            "humorous_non_tech": captions.get("humorous_non_tech", SAFE_FALLBACKS["humorous_non_tech"]),
            "recommended_style": recommended_style,
            "reasoning": reasoning,
            "confidence": confidence,
            "grounding_branch": grounding_branch,
            "transcript_preview": transcript[:500] if transcript else "",
            "factual_description_preview": factual_description[:500],
            "verification": {
                "confirmed": grounding_verification.get("confirmed", []) if grounding_verification else [],
                "unconfirmed": grounding_verification.get("unconfirmed", []) if grounding_verification else [],
                "per_caption_issues": grounding_verification.get("per_caption_issues", {}) if grounding_verification else {},
            },
            "timings": timings,
        }

        return output_data


def download_video(url, dest_path):
    """Download a video from a URL to a local path."""
    logger.info(f"Downloading video from {url} ...")
    try:
        resp = requests.get(url, stream=True, timeout=300)
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        logger.info(f"Downloaded {os.path.getsize(dest_path)} bytes -> {dest_path}")
    except Exception as e:
        logger.error(f"Video download failed: {e}")
        raise


def format_task_output(pipeline_result, task, input_mode):
    """Attach task metadata to pipeline output."""
    output = dict(pipeline_result)
    output["task_id"] = task.get("task_id", "unknown")
    if input_mode == "tasks_json" and "video_url" in task:
        output["video_url"] = task["video_url"]
    return output


def process_task(task, input_mode):
    """Download or resolve video path, run pipeline, return formatted output."""
    task_id = task.get("task_id", "unknown")
    with tempfile.TemporaryDirectory() as temp_dir:
        if input_mode == "tasks_json":
            suffix = ".mp4"
            video_path = os.path.join(temp_dir, f"{task_id}{suffix}")
            download_video(task["video_url"], video_path)
        else:
            video_path = task["video_path"]

        pipeline_result = process_single_video(video_path)
        return format_task_output(pipeline_result, task, input_mode)


def run_batch_mode(args):
    """Batch CLI mode: auto-detect input, process all tasks, write results."""
    check_dependencies()

    output_path = args.output or OUTPUT_PATH
    input_mode, tasks = load_tasks()

    if not tasks:
        write_results([], output_path)
        logger.info(f"Initialized empty JSON manifest at: {output_path}")
        return

    logger.info(f"Autonomous runner initialized. Processing {len(tasks)} task(s) in {input_mode} mode.")
    cumulative_results = []

    for idx, task in enumerate(tasks):
        task_id = task.get("task_id", f"task_{idx}")
        try:
            logger.info(f"=== Process [{idx + 1}/{len(tasks)}]: {task_id} ===")
            result = process_task(task, input_mode)
            cumulative_results.append(result)
        except Exception as e:
            logger.error(f"CRITICAL error processing {task_id}: {e}. Applying fallback.")
            fallback = fallback_task_result(task_id)
            cumulative_results.append(format_task_output(fallback, task, input_mode))

        write_results(cumulative_results, output_path)
        logger.info(f"Incremental write: {len(cumulative_results)} result(s) -> {output_path}")

    if input_mode == "folder":
        write_folder_per_video_outputs(cumulative_results, OUTPUT_DIR)

    logger.info("=" * 60)
    logger.info("BATCH PROCESS COMPLETE.")
    logger.info(f"--> {output_path}")
    logger.info("=" * 60)

def main():
    parser = argparse.ArgumentParser(description="FourVoice Captioner - Autonomous Pipeline")
    parser.add_argument(
        "--input-dir",
        default=None,
        help="Override INPUT_DIR for folder mode (default: env INPUT_DIR or ./input)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Override OUTPUT_PATH (default: env OUTPUT_PATH or ./output/results.json)",
    )
    args = parser.parse_args()

    global INPUT_DIR, OUTPUT_PATH
    if args.input_dir:
        INPUT_DIR = args.input_dir
    if args.output:
        OUTPUT_PATH = args.output

    run_batch_mode(args)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Fatal startup error: {e}")
        sys.exit(1)
