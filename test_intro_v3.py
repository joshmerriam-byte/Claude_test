#!/usr/bin/env python3
"""Intro test v3 - longer fades, same concepts as transition v4."""

import os
import base64
import subprocess
import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleAuthRequest

CREDENTIALS_PATH = "/home/user/Claude_test/gcp_credentials.json"
OUTPUT_DIR = "/home/user/Claude_test"
TTS_MODEL = "gemini-2.5-flash-preview-tts"

ALEX_PROMPT = "(Claude to be pronounced like it rhymes with fraud, and Anthropic pronounced like an·thraa·puhk) Read aloud in a warm, welcoming tone"

# First line of intro
FIRST_LINE = "So Jamie, I want to tell you about, um, an impossible job."

credentials = service_account.Credentials.from_service_account_file(
    CREDENTIALS_PATH, scopes=["https://www.googleapis.com/auth/cloud-platform"])
credentials.refresh(GoogleAuthRequest())
access_token = credentials.token

def generate_speech(text):
    url = "https://texttospeech.googleapis.com/v1beta1/text:synthesize"
    payload = {
        "audioConfig": {"audioEncoding": "MP3", "pitch": 0, "speakingRate": 1.2},
        "input": {"text": text, "prompt": ALEX_PROMPT},
        "voice": {"languageCode": "en-US", "modelName": TTS_MODEL, "name": "Aoede"},
    }
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    
    for attempt in range(5):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=180)
            if response.status_code == 200:
                return base64.b64decode(response.json()["audioContent"])
        except:
            pass
        import time; time.sleep(2 ** attempt)
    raise Exception("Failed")

print("Generating first line...")
speech = generate_speech(FIRST_LINE)
speech_path = os.path.join(OUTPUT_DIR, "intro_v3_speech.mp3")
with open(speech_path, "wb") as f:
    f.write(speech)

MUSIC_PATH = os.path.join(OUTPUT_DIR, "intro_music_8s.mp3")
OUTPUT = os.path.join(OUTPUT_DIR, "test_intro_v3.mp3")

# Structure: 3s of music alone, then speech starts, music fades out underneath
# Longer fade in (2s), longer fade out (3s)
print("Mixing intro with longer fades...")
cmd = [
    "ffmpeg", "-y",
    "-i", speech_path,
    "-i", MUSIC_PATH,
    "-filter_complex",
    # Music: fade in 2s, fade out starting at 5s over 3s
    "[1:a]afade=t=in:st=0:d=2,afade=t=out:st=5:d=3,volume=0.7[music];"
    # Speech delayed 3s
    "[0:a]adelay=3000|3000[speech];"
    # Mix
    "[music][speech]amix=inputs=2:duration=longest:weights=1 1:normalize=0",
    "-acodec", "libmp3lame", "-q:a", "2",
    OUTPUT
]
result = subprocess.run(cmd, capture_output=True, text=True)
if result.returncode != 0:
    print(f"Error: {result.stderr}")
else:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", OUTPUT],
        capture_output=True, text=True)
    print(f"Created: {OUTPUT}")
    print(f"Duration: {float(result.stdout.strip()):.1f}s")
