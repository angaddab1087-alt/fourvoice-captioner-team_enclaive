"""Unit test for clean_caption_output with real deepseek-v4-pro output."""
import sys
sys.path.insert(0, r'a:\AMD\fourvoice-captioner')
from fourvoice_captioner import clean_caption_output, is_valid_caption

# Test 1: Real sarcastic output from deepseek-v4-pro
raw_sarcastic = (
    'We are asked: "Write a single dry, sarcastic caption reacting to this clip, '
    'under 25 words. Ironic/witty, never cruel, must stay clearly connected to the '
    'actual clip content. Base this only on the factual description provided."\n\n'
    'The factual description: "A screen recording showing someone navigating the '
    'Fireworks AI website, clicking Create API Key, typing the name My_First_API_Key, '
    'generating the key, and copying it to clipboard."\n\n'
    'We need a dry, sarcastic caption, under 25 words.\n\n'
    'Possible caption: "Ah yes, \'My First API Key\'\u2014right next to the festive '
    'garment key. Truly groundbreaking naming conventions."\n\n'
    'Count words: that is 15 words. Under 25.\n\n'
    'Another: "Naming your API key \'My_First_API_Key\' is bold creativity from '
    'someone who also has \'Ugly_Holiday_Sweater_HF_Space\'."\n\n'
    'Word count: 19 words.'
)

# Test 2: Clean output that needs no extraction
raw_clean = 'The video displays a uniform green screen throughout its entire duration.'

# Test 3: Formal output with reasoning
raw_formal = (
    'We are asked: "Write a single neutral, professional, factual caption..."\n\n'
    'The description mentions navigating the Fireworks AI website.\n\n'
    'Possible caption: "A screen recording demonstrates the process of creating '
    'and copying a new API key on the Fireworks AI platform."\n\n'
    'That is 18 words.'
)

tests = [
    ("sarcastic", raw_sarcastic, 25),
    ("clean", raw_clean, 40),
    ("formal", raw_formal, 40),
]

for name, raw, max_w in tests:
    result = clean_caption_output(raw, max_words=max_w)
    valid = is_valid_caption(result, max_words=max_w)
    print(f"[{name}] {'PASS' if valid else 'FAIL'}: {result!r}")
    print()
