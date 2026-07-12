"""Test HuggingFace Inference API with fal-ai provider for Whisper ASR."""
import os
import sys
import time

# Allow passing HF_TOKEN as argument or env var
hf_token = os.environ.get("HF_TOKEN") or (sys.argv[1] if len(sys.argv) > 1 else None)
if not hf_token:
    print("ERROR: Set HF_TOKEN env var or pass as argument")
    sys.exit(1)

from huggingface_hub import InferenceClient

# Test with our downloaded audio file
audio_file = "test_audio.flac"
if not os.path.exists(audio_file):
    print(f"ERROR: {audio_file} not found")
    sys.exit(1)

print(f"Audio file: {audio_file} ({os.path.getsize(audio_file)} bytes)")
print(f"HF_TOKEN: {hf_token[:6]}...{hf_token[-4:]}")
print()

# Test 1: fal-ai provider
print("=== Test 1: fal-ai provider / whisper-large-v3 ===")
t0 = time.time()
try:
    client = InferenceClient(provider="fal-ai", api_key=hf_token)
    output = client.automatic_speech_recognition(audio_file, model="openai/whisper-large-v3")
    elapsed = time.time() - t0
    print(f"  Time: {elapsed:.2f}s")
    print(f"  Type: {type(output)}")
    print(f"  Text: {output.text[:300] if hasattr(output, 'text') else str(output)[:300]}")
except Exception as e:
    elapsed = time.time() - t0
    print(f"  FAILED ({elapsed:.2f}s): {e}")

print()

# Test 2: Try default provider (HF Inference API)
print("=== Test 2: default provider / whisper-large-v3 ===")
t0 = time.time()
try:
    client2 = InferenceClient(api_key=hf_token)
    output2 = client2.automatic_speech_recognition(audio_file, model="openai/whisper-large-v3")
    elapsed = time.time() - t0
    print(f"  Time: {elapsed:.2f}s")
    print(f"  Type: {type(output2)}")
    print(f"  Text: {output2.text[:300] if hasattr(output2, 'text') else str(output2)[:300]}")
except Exception as e:
    elapsed = time.time() - t0
    print(f"  FAILED ({elapsed:.2f}s): {e}")
