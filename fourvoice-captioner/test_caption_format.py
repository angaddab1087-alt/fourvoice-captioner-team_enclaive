"""Quick test: does the CAPTION: format instruction work with deepseek-v4-pro?"""
import requests, time, os

key = os.environ.get('FIREWORKS_API_KEY', '')
if not key:
    raise SystemExit("Set FIREWORKS_API_KEY environment variable")
model = 'accounts/fireworks/models/deepseek-v4-pro'
desc = ('This is a screen recording of the Fireworks AI website, showing a dark-themed '
        'user interface with purple and orange accents. The user navigates to the API Keys '
        'management page, clicks a yellow Create API Key button, types My_First_API_Key as '
        'the key name in a modal dialog, generates the key, copies the value from a modal, '
        'then returns to the list view showing the new key alongside an existing key named '
        'Ugly_Holiday_Sweater_HF_Space. The clip ends with a branded end card displaying '
        'the Fireworks AI logo and tagline.')

styles = {
    'sarcastic': (
        'Write a single dry, sarcastic caption reacting to this clip, under 25 words. '
        'Ironic/witty, never cruel, must stay clearly connected to the actual clip content.'
    ),
    'humorous_tech': (
        'Write a single funny caption using tech/developer culture humor, under 25 words. '
        'The caption MUST contain a real joke tied to a specific detail from the description.'
    ),
}

for style, prompt in styles.items():
    sys_msg = (
        f"{prompt}\n"
        "Base this only on the factual description provided.\n"
        'You may think through your approach, but your FINAL line must be exactly:\n'
        'CAPTION: "your caption here"\n'
        "Nothing may follow the CAPTION line."
    )
    msgs = [
        {'role': 'system', 'content': sys_msg},
        {'role': 'user', 'content': f'Factual Description:\n{desc}'}
    ]
    t0 = time.time()
    r = requests.post('https://api.fireworks.ai/inference/v1/chat/completions',
        headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
        json={'model': model, 'messages': msgs, 'temperature': 0.8, 'max_tokens': 2048},
        timeout=30)
    elapsed = time.time() - t0
    content = r.json()['choices'][0]['message']['content']
    
    # Extract CAPTION: line
    import re
    m = re.search(r'^CAPTION:\s*"(.+?)"\s*$', content, re.MULTILINE)
    caption = m.group(1) if m else "NOT FOUND"
    
    print(f"[{style}] ({elapsed:.1f}s, {len(content)} chars)")
    print(f"  CAPTION: {caption}")
    print(f"  Last 200 chars: ...{content[-200:]}")
    print()
