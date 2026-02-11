#!/usr/bin/env python3
"""Generate transition test v3 - music overlays end of Alex's line."""

import os
import base64
import subprocess
import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleAuthRequest

CREDENTIALS_PATH = "/home/user/Claude_test/gcp_credentials.json"
OUTPUT_DIR = "/home/user/Claude_test"
TTS_MODEL = "gemini-2.5-flash-preview-tts"

VOICES = {
    "ALEX": {
        "name": "Aoede",
        "prompt": "(Claude to be pronounced like it rhymes with fraud, and Anthropic pronounced like an·thraa·puhk) Read aloud in a warm, welcoming tone",
    },
    "JAMIE": {
        "name": "Algenib", 
        "prompt": "(Claude to be pronounced like it rhymes with fraud, and Anthropic pronounced like an·thraa·puhk) Read aloud with a cool, thoughtful, British accent",
    },
}

# Full Alex line - will NOT fade out the voice
ALEX_LINE = ("ALEX", "It's a twenty-four-hundred-year-old shift. She was, um, rediscovering virtue ethics.")
JAMIE_LINE = ("JAMIE", "Okay, virtue ethics. Give me the quick version.")

credentials = service_account.Credentials.from_service_account_file(
    CREDENTIALS_PATH, scopes=["https://www.googleapis.com/auth/cloud-platform"])
credentials.refresh(GoogleAuthRequest())
access_token = credentials.token

def generate_speech(text, speaker):
    url = "https://texttospeech.googleapis.com/v1beta1/text:synthesize"
    voice = VOICES[speaker]
    payload = {
        "audioConfig": {"audioEncoding": "MP3", "pitch": 0, "speakingRate": 1.2},
        "input": {"text": text, "prompt": voice["prompt"]},
        "voice": {"languageCode": "en-US", "modelName": TTS_MODEL, "name": voice["name"]},
    }
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    
    for attempt in range(5):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=180)
            if response.status_code == 200:
                return base64.b64decode(response.json()["audioContent"])
            print(f"  Error {response.status_code}, retrying...")
        except requests.exceptions.Timeout:
            print(f"  Timeout, retrying...")
        import time; time.sleep(2 ** attempt)
    raise Exception("Failed to generate speech")

print("Generating Alex's full line...")
alex_audio = generate_speech(ALEX_LINE[1], ALEX_LINE[0])
alex_path = os.path.join(OUTPUT_DIR, "trans_v3_alex.mp3")
with open(alex_path, "wb") as f:
    f.write(alex_audio)

print("Generating Jamie's line...")
jamie_audio = generate_speech(JAMIE_LINE[1], JAMIE_LINE[0])
jamie_path = os.path.join(OUTPUT_DIR, "trans_v3_jamie.mp3")
with open(jamie_path, "wb") as f:
    f.write(jamie_audio)

# Get Alex duration
result = subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
     "-of", "default=noprint_wrappers=1:nokey=1", alex_path],
    capture_output=True, text=True)
alex_dur = float(result.stdout.strip())
print(f"Alex duration: {alex_dur:.2f}s")

# Music starts 2 seconds BEFORE Alex ends (overlapping)
# Music fades in, plays under her last words, then continues after
MUSIC_PATH = os.path.join(OUTPUT_DIR, "transition_raw.mp3")
OUTPUT = os.path.join(OUTPUT_DIR, "test_transition_v3.mp3")

music_start_time = max(0, alex_dur - 2)  # Start music 2s before Alex ends
music_start_ms = int(music_start_time * 1000)

# Jamie starts: after Alex ends + music (5s) + 1.5s tension
jamie_start_ms = int((alex_dur + 5 + 1.5) * 1000)

print(f"Music starts at: {music_start_ms}ms (overlapping last 2s of Alex)")
print(f"Jamie starts at: {jamie_start_ms}ms")

# Mix: Alex at full volume (no fade), music fades in under her, Jamie after gap
cmd = [
    "ffmpeg", "-y",
    "-i", alex_path,       # 0: Alex (full, no fade)
    "-i", MUSIC_PATH,      # 1: transition music (raw, loud)
    "-i", jamie_path,      # 2: Jamie
    "-filter_complex",
    # Alex stays at full volume, pad to allow music after
    f"[0:a]apad=pad_dur=7[alex];"
    # Music: fade in over 1s, starts overlapping Alex, stays loud
    f"[1:a]afade=t=in:st=0:d=1,afade=t=out:st=4:d=1,adelay={music_start_ms}|{music_start_ms}[music];"
    # Jamie delayed
    f"[2:a]adelay={jamie_start_ms}|{jamie_start_ms}[jamie];"
    # Mix - don't normalize, keep volumes as-is
    f"[alex][music][jamie]amix=inputs=3:duration=longest:weights=1 0.8 1:normalize=0",
    "-acodec", "libmp3lame", "-q:a", "2",
    OUTPUT
]

print("Mixing...")
result = subprocess.run(cmd, capture_output=True, text=True)
if result.returncode != 0:
    print(f"FFmpeg error: {result.stderr}")
else:
    # Get duration
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", OUTPUT],
        capture_output=True, text=True)
    print(f"Created: {OUTPUT}")
    print(f"Duration: {float(result.stdout.strip()):.1f}s")
