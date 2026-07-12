#!/usr/bin/env python3
"""
FourVoice Captioner - AMD Developer Hackathon ACT II, Track 2 (Video Captioning)
Fully autonomous containerized Python pipeline.
"""

import os
import sys
import json
import math
import glob
import logging
import argparse
import subprocess
import tempfile
import base64
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
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY")

# Choose current optimal Fireworks models at build time
WHISPER_MODEL = "accounts/fireworks/models/whisper-v3"
GEMMA_VISION_MODEL = "accounts/fireworks/models/gemma2-9b-it"  # or other active Gemma visual/chat model
CHAT_WRITING_MODEL = "accounts/fireworks/models/llama-v3-70b-instruct" # Qwen, Llama or Minimax for creative styling

def check_dependencies():
    """Ensure ffmpeg is installed and API keys are available."""
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("ffmpeg is not installed or available in PATH. Please verify your system setup.")
        sys.exit(1)
        
    if not FIREWORKS_API_KEY:
        logger.error("FIREWORKS_API_KEY environment variable is not set. Exiting.")
        sys.exit(1)

def fireworks_chat_completion(model, messages, temperature=0.7, max_tokens=1024, json_mode=False):
    """Call Fireworks Chat Completion API."""
    headers = {
        "Authorization": f"Bearer {FIREWORKS_API_KEY}",
        "Content-Type": "application/json"
    }
    url = f"{FIREWORKS_BASE_URL}/chat/completions"
    
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
        
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        res_json = response.json()
        return res_json["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"API request failed to model {model}: {e}")
        raise

def transcribe_audio_whisper(audio_path):
    """Send extracted audio to Fireworks Whisper v3 STT."""
    headers = {
        "Authorization": f"Bearer {FIREWORKS_API_KEY}"
    }
    url = f"{FIREWORKS_BASE_URL}/audio/transcriptions"
    
    try:
        with open(audio_path, "rb") as f:
            files = {
                "file": (os.path.basename(audio_path), f, "audio/mpeg"),
            }
            data = {
                "model": WHISPER_MODEL,
                "response_format": "json"
            }
            response = requests.post(url, files=files, data=data, headers=headers, timeout=90)
            response.raise_for_status()
            res_json = response.json()
            return res_json.get("text", "")
    except Exception as e:
        logger.error(f"Whisper STT transcription failed: {e}")
        return ""

def calculate_word_diversity(text):
    """Calculate basic word diversity to identify song lyrics/monotonous loops."""
    words = [w.lower().strip(".,?!\"'()") for w in text.split() if w]
    if not words:
        return 0.0
    unique_words = set(words)
    # Ratio of unique words to total words
    return len(unique_words) / len(words)

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

def extract_frames(video_path, temp_dir, num_frames=10):
    """Extract evenly spaced frames from video using ffmpeg."""
    # Find duration first
    duration_cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", video_path
    ]
    try:
        res = subprocess.run(duration_cmd, capture_output=True, text=True, check=True)
        duration = float(res.stdout.strip())
    except Exception as e:
        logger.warning(f"Failed to probe duration, defaulting to 10s: {e}")
        duration = 10.0

    frame_paths = []
    interval = duration / (num_frames + 1)
    
    for i in range(1, num_frames + 1):
        timestamp = i * interval
        frame_name = f"frame_{i:02d}.jpg"
        frame_path = os.path.join(temp_dir, frame_name)
        cmd = [
            "ffmpeg", "-y", "-ss", str(timestamp), "-i", video_path,
            "-vframes", "1", "-q:v", "2", frame_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        if os.path.exists(frame_path):
            frame_paths.append(frame_path)
            
    logger.info(f"Extracted {len(frame_paths)} frames for multimodal analysis.")
    return frame_paths

def analyze_frames_gemma(frame_paths, partial_transcript=""):
    """
    Send extracted frame images to Gemma Vision-Multimodal model.
    Encodes images into base64 and formats the request.
    """
    # In Fireworks Gemma-vision, we can pass images in Chat Completions with base64 data URIs
    parts = []
    
    text_content = (
        f"Describe factually and neutrally what is visible across these frames: "
        f"setting, subjects, actions, any on-screen text or style (e.g., illustrated/comic panel vs. live action). "
        f"Do not guess or hallucinate anything not visibly present. If this appears to be a music/performance "
        f"video or a static image with background music, describe the visual content as-is."
    )
    if partial_transcript:
        text_content += f"\nNote: Here is a partial transcription of the audio for visual-text grounding: \"{partial_transcript}\""
        
    parts.append({"type": "text", "text": text_content})
    
    # Send up to 3 key frames to prevent token limit issues, selecting beginning, middle, and end frames
    indices = [0, len(frame_paths)//2, len(frame_paths)-1]
    selected_frames = [frame_paths[idx] for idx in indices if 0 <= idx < len(frame_paths)]
    
    for idx, path in enumerate(selected_frames):
        with open(path, "rb") as image_file:
            base64_data = base64.b64encode(image_file.read()).decode("utf-8")
            parts.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_data}"
                }
            })
            
    messages = [
        {
            "role": "user",
            "content": parts
        }
    ]
    
    logger.info(f"Calling Gemma vision-multimodal model ({GEMMA_VISION_MODEL})...")
    description = fireworks_chat_completion(GEMMA_VISION_MODEL, messages, temperature=0.2)
    return description

def process_single_video(video_path):
    """Run full 9-stage video processing pipeline on a single clip."""
    logger.info(f"============================================================")
    logger.info(f"PROCESSING VIDEO: {os.path.basename(video_path)}")
    logger.info(f"============================================================")
    
    # Establish default safe fallback results to return if any stage completely errors out
    fallback_results = {
        "video": os.path.basename(video_path),
        "formal": "The video clip features visual elements with accompanying background sound.",
        "sarcastic": "Wow, a video with pixels and noise. Truly revolutionary work.",
        "humorous_tech": "404: Audio track context not found. Refactored back to a generic description array.",
        "humorous_non_tech": "Just your standard video clip doing normal video clip things.",
        "recommended_style": "formal",
        "reasoning": "Fallback default applied due to execution interruption or missing signal.",
        "confidence": 0.30
    }
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # STAGE 1 — Audio transcription
        transcript = ""
        word_count = 0
        try:
            audio_path = extract_audio(video_path, temp_dir)
            transcript = transcribe_audio_whisper(audio_path)
            words = [w for w in transcript.split() if w]
            word_count = len(words)
            logger.info(f"STAGE 1: whisper transcription complete. Real words count: {word_count}")
            logger.info(f"Transcript preview: \"{transcript[:150]}...\"" if transcript else "Empty transcript.")
        except Exception as e:
            logger.error(f"STAGE 1 (Audio transcription) failed: {e}. Attempting vision pipeline directly.")
            
        # STAGE 2 — Audio-informativeness check
        # >15 real words, and word diversity > 0.45 (repetitive lyrics check)
        is_audio_informative = False
        if word_count > 15:
            diversity = calculate_word_diversity(transcript)
            logger.info(f"STAGE 2: Diversity score = {diversity:.2f} (unique-to-total ratio)")
            if diversity >= 0.40:
                is_audio_informative = True
                logger.info("STAGE 2 Decision: Audio is INFORMATIVE. Branching to STAGE 3A (Audio-grounded).")
            else:
                logger.info("STAGE 2 Decision: Audio is REPETITIVE/LYRICAL. Branching to STAGE 3B (Vision-grounded).")
        else:
            logger.info("STAGE 2 Decision: Audio is INSUFFICIENT (<15 words). Branching to STAGE 3B (Vision-grounded).")
            
        # STAGE 3 — Factual Description (A or B)
        factual_description = ""
        if is_audio_informative:
            # STAGE 3A — Audio-grounded factual description
            try:
                system_prompt = (
                    "Based on this transcript, write a neutral, factual, detailed description of what is happening in this video clip. "
                    "State only what is directly evidenced by the transcript. Do not invent visual details you cannot know from audio alone."
                )
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Transcript:\n{transcript}"}
                ]
                logger.info("STAGE 3A: Calling Fireworks chat model for audio-grounded description...")
                factual_description = fireworks_chat_completion(CHAT_WRITING_MODEL, messages, temperature=0.1)
                logger.info(f"Factual Description: {factual_description[:150]}...")
            except Exception as e:
                logger.error(f"STAGE 3A failed: {e}. Falling back to vision.")
                is_audio_informative = False # Force vision fallback if STT model crashed
                
        if not is_audio_informative or not factual_description:
            # STAGE 3B — Vision-grounded factual description
            try:
                frame_paths = extract_frames(video_path, temp_dir, num_frames=8)
                factual_description = analyze_frames_gemma(frame_paths, partial_transcript=transcript)
                logger.info(f"STAGE 3B Vision-Grounded Description: {factual_description[:150]}...")
            except Exception as e:
                logger.error(f"STAGE 3B failed: {e}. Using combined fallback texts.")
                factual_description = "The clip depicts visual movement, scene transitions, and ambient audio."
                if transcript:
                    factual_description += f" Handled partial audio: {transcript}"

        # STAGE 4 — Four-style caption generation
        captions = {}
        style_prompts = {
            "formal": "Write a single neutral, professional, factual caption describing this clip in 1-2 sentences. Third person, no opinion, no humor.",
            "sarcastic": "Write a single dry, sarcastic caption reacting to this clip, under 25 words. Ironic/witty, never cruel, must stay clearly connected to the actual clip content.",
            "humorous_tech": "Write a single funny caption using tech/developer culture humor (jargon, memes, dev-life references), under 25 words. Must still describe what's actually happening in the clip, not a generic unrelated tech joke.",
            "humorous_non_tech": "Write a single funny, broadly relatable caption with everyday humor, under 25 words. No tech references. Must stay grounded in the actual clip content."
        }
        
        for style, prompt in style_prompts.items():
            try:
                system_instruction = (
                    f"{prompt}\n"
                    "Base this only on the factual description provided. Do not introduce any fact, detail, or claim not present in that description."
                )
                messages = [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": f"Factual Description:\n{factual_description}"}
                ]
                logger.info(f"STAGE 4: Generating '{style}' style caption...")
                captions[style] = fireworks_chat_completion(CHAT_WRITING_MODEL, messages, temperature=0.8).strip().strip('"')
                logger.info(f"  Result: \"{captions[style]}\"")
            except Exception as e:
                logger.error(f"STAGE 4 failed to generate {style} style: {e}")
                captions[style] = fallback_results[style]

        # STAGE 5 — Self-QC pass
        for style in style_prompts.keys():
            try:
                qc_prompt = (
                    "You are an internal quality control judge. Assess this generated caption against the source facts.\n"
                    "Grade on two axes:\n"
                    "1. Factual accuracy: Does it avoid introducing any hallucinations or unevidenced facts from outside the description? (1 to 5)\n"
                    "2. Tone accuracy: Does it genuinely, distinctly match its intended tone style (formal, sarcastic, humorous_tech, humorous_non_tech)? (1 to 5)\n"
                    "Format your response strictly as JSON with this schema:\n"
                    '{"factual_accuracy": 5, "tone_accuracy": 5, "explanation": "..."}'
                )
                
                messages = [
                    {"role": "system", "content": qc_prompt},
                    {"role": "user", "content": f"Factual source description:\n{factual_description}\n\nGenerated caption ({style}):\n\"{captions[style]}\""}
                ]
                
                qc_res_raw = fireworks_chat_completion(CHAT_WRITING_MODEL, messages, temperature=0.1, json_mode=True)
                qc_res = json.loads(qc_res_raw)
                fact_score = qc_res.get("factual_accuracy", 3)
                tone_score = qc_res.get("tone_accuracy", 3)
                logger.info(f"STAGE 5: QC Check for '{style}' -> Fact Score: {fact_score}/5, Tone Score: {tone_score}/5")
                
                if fact_score < 3 or tone_score < 3:
                    logger.warning(f"QC Score too low ({fact_score}/5, {tone_score}/5). STAGE 5: Regenerating caption with sharper prompt...")
                    regenerate_system = (
                        f"{style_prompts[style]}\n"
                        "CRITICAL: Your previous attempt failed QC checks. Keep it STRICTLY grounded. "
                        "Double down on the tone. Do NOT add outside facts. Stay under 25 words."
                    )
                    messages_retry = [
                        {"role": "system", "content": regenerate_system},
                        {"role": "user", "content": f"Factual Description:\n{factual_description}"}
                    ]
                    captions[style] = fireworks_chat_completion(CHAT_WRITING_MODEL, messages_retry, temperature=0.9).strip().strip('"')
                    logger.info(f"  Regenerated '{style}' Result: \"{captions[style]}\"")
            except Exception as e:
                logger.error(f"STAGE 5: QC pass failed for {style}: {e}. Retaining original.")

        # STAGE 6 — Best-fit tone recommendation
        recommended_style = "formal"
        reasoning = ""
        try:
            rec_prompt = (
                "Given this factual description of the clip, which of these four tones — formal, sarcastic, humorous_tech, humorous_non_tech — best matches the clip's natural emotional register?\n"
                "Format your answer strictly as JSON with the following schema:\n"
                '{"recommended_style": "sarcastic", "reasoning": "A short, one-sentence reason."}'
            )
            messages = [
                {"role": "system", "content": rec_prompt},
                {"role": "user", "content": f"Factual description:\n{factual_description}"}
            ]
            logger.info("STAGE 6: Querying best-fit tone recommendation...")
            rec_res_raw = fireworks_chat_completion(CHAT_WRITING_MODEL, messages, temperature=0.2, json_mode=True)
            rec_res = json.loads(rec_res_raw)
            recommended_style = rec_res.get("recommended_style", "formal")
            # Normalize key
            if recommended_style == "humorous-tech":
                recommended_style = "humorous_tech"
            elif recommended_style == "humorous-non-tech":
                recommended_style = "humorous_non_tech"
            reasoning = rec_res.get("reasoning", "Matches the overall pace and subject matter of the footage.")
            logger.info(f"STAGE 6: Recommended Tone: {recommended_style} | Reason: {reasoning}")
        except Exception as e:
            logger.error(f"STAGE 6: Best-fit recommendation failed: {e}")
            reasoning = "Neutral professional assessment is safest for ambiguous contexts."

        # STAGE 7 — Confidence scoring
        # Calculate based on audio-first vs vision fallback branch & description richness
        confidence = 0.50
        try:
            if is_audio_informative:
                # Spoken audio is direct evidence (high confidence)
                confidence = 0.85 + (min(word_count, 100) / 1000.0)
            else:
                # Vision-only represents visual inferences (medium confidence)
                confidence = 0.60 + (min(len(factual_description), 300) / 1000.0)
            confidence = min(round(confidence, 2), 1.0)
            logger.info(f"STAGE 7: Calculated Pipeline Confidence = {confidence}")
        except Exception as e:
            logger.error(f"STAGE 7: Confidence scoring failed: {e}")
            confidence = 0.75

        # STAGE 8 — Output Assembly
        output_data = {
            "video": os.path.basename(video_path),
            "formal": captions.get("formal", fallback_results["formal"]),
            "sarcastic": captions.get("sarcastic", fallback_results["sarcastic"]),
            "humorous_tech": captions.get("humorous_tech", fallback_results["humorous_tech"]),
            "humorous_non_tech": captions.get("humorous_non_tech", fallback_results["humorous_non_tech"]),
            "recommended_style": recommended_style,
            "reasoning": reasoning,
            "confidence": confidence
        }
        return output_data

def main():
    parser = argparse.ArgumentParser(description="FourVoice Captioner - Autonomous Batch Pipeline")
    parser.add_argument("--input-dir", default="./input", help="Directory containing input video files (mp4, mov, etc.)")
    parser.add_argument("--output", default="./output/results.json", help="Expected JSON path to write cumulative results")
    args = parser.parse_args()
    
    check_dependencies()
    
    # Establish inputs & outputs
    input_dir = args.input_dir
    output_path = args.output
    
    # Ensure output folders exist
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    
    # Locate all compatible video files in the target directory
    video_extensions = ["*.mp4", "*.mov", "*.avi", "*.mkv", "*.webm", "*.MP4", "*.MOV"]
    video_files = []
    for ext in video_extensions:
        video_files.extend(glob.glob(os.path.join(input_dir, ext)))
        
    # De-duplicate files
    video_files = list(set(video_files))
    
    if not video_files:
        logger.warning(f"No video files found in input folder '{input_dir}'.")
        # Write an empty results manifest to prevent scoring failure
        with open(output_path, "w") as f:
            json.dump([], f, indent=2)
        logger.info(f"Initialized empty JSON manifest at: {output_path}")
        return
        
    logger.info(f"Autonomous runner initialized. Found {len(video_files)} video clips to process.")
    
    cumulative_results = []
    
    # Process files sequentially
    for idx, video_path in enumerate(video_files):
        try:
            logger.info(f"=== Process Clip [{idx+1}/{len(video_files)}]: {os.path.basename(video_path)} ===")
            result = process_single_video(video_path)
            cumulative_results.append(result)
        except Exception as e:
            # STAGE 0 exception protection - never crash the run
            logger.error(f"CRITICAL Error processing {os.path.basename(video_path)}: {e}. Applying high-level fallback.")
            safe_fallback = {
                "video": os.path.basename(video_path),
                "formal": "The video segment contains technical media configurations.",
                "sarcastic": "Wow, a totally unprocessable file. Brilliant encoding.",
                "humorous_tech": "Pipeline error: Exception thrown in Main Thread. Catch block executed.",
                "humorous_non_tech": "A video that has a hard time running on standard pipelines.",
                "recommended_style": "formal",
                "reasoning": "Pipeline encountered a critical driver or file-corruption error.",
                "confidence": 0.10
            }
            cumulative_results.append(safe_fallback)
            
    # STAGE 8 - Write output to results.json manifest
    try:
        with open(output_path, "w") as f:
            json.dump(cumulative_results, f, indent=2)
        logger.info(f"============================================================")
        logger.info(f"BATCH PROCESS COMPLETE. Cumulative results written to:")
        logger.info(f"--> {output_path}")
        logger.info(f"============================================================")
    except Exception as e:
        logger.error(f"Failed to write final JSON manifest output to {output_path}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
