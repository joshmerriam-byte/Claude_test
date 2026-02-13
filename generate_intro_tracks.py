#!/usr/bin/env python3
"""Generate separate tracks for Audacity import."""

import os
import base64
import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleAuthRequest

CREDENTIALS_PATH = "/home/user/Claude_test/gcp_credentials.json"
OUTPUT_DIR = "/home/user/Claude_test/intro_tracks"
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

# First several lines from the intro
LINES = [
    ("ALEX", "So Jamie, I want to tell you about, um, an impossible job."),
    ("JAMIE", "I'm listening."),
    ("ALEX", "For the first time in history, humans tried to teach something non-human how to be good. And they wrote an eighty-page document to do it."),
    ("JAMIE", "Eighty pages to teach an AI morality."),
    ("ALEX", "Imagine you're a philosopher. You have a PhD, you've spent years thinking about ethics and moral reasoning. And then a company hires you and says: we need you to write a document that will teach an artificial intelligence how to be good."),
]

os.makedirs(OUTPUT_DIR, exist_ok=True)

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
        except Exception as e:
            print(f"  Exception: {e}, retrying...")
        import time; time.sleep(2 ** attempt)
    raise Exception("Failed to generate speech")

# Generate each line as separate file
print("Generating individual speech tracks...")
for i, (speaker, text) in enumerate(LINES):
    filename = f"{i+1:02d}_{speaker.lower()}.mp3"
    filepath = os.path.join(OUTPUT_DIR, filename)
    print(f"  {filename}: {text[:50]}...")
    audio = generate_speech(text, speaker)
    with open(filepath, "wb") as f:
        f.write(audio)

# Copy music file to the folder
import shutil
shutil.copy("/home/user/Claude_test/intro_music_12s.mp3", os.path.join(OUTPUT_DIR, "00_music_intro.mp3"))

print(f"\nFiles created in {OUTPUT_DIR}/:")
for f in sorted(os.listdir(OUTPUT_DIR)):
    print(f"  {f}")

print("\n=== AUDACITY IMPORT INSTRUCTIONS ===")
print("1. Open Audacity")
print("2. File > Import > Audio (Ctrl+Shift+I)")
print("3. Select all files in intro_tracks/ folder")
print("4. Each file will appear on its own track")
print("5. Drag tracks to adjust timing")
print("\nSuggested timing:")
print("  00_music_intro.mp3 - starts at 0:00")
print("  01_alex.mp3 - starts at ~3:00 (3 seconds)")
print("  02_jamie.mp3 - after 01_alex ends")
print("  etc.")
