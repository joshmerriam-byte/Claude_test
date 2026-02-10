#!/usr/bin/env python3
"""Test intro music mixing with first line of dialogue."""

import os
import base64
import subprocess
import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleAuthRequest

CREDENTIALS_PATH = "/home/user/Claude_test/gcp_credentials.json"
MUSIC_INTRO = "/home/user/Claude_test/music_intro_v2.mp3"
OUTPUT_DIR = "/home/user/Claude_test"

# Get access token
credentials = service_account.Credentials.from_service_account_file(
    CREDENTIALS_PATH,
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)
credentials.refresh(GoogleAuthRequest())
access_token = credentials.token

# Generate first line
text = "So Jamie, I want to tell you about, um, an impossible job."
print(f"Generating speech: {text}")

url = "https://texttospeech.googleapis.com/v1beta1/text:synthesize"
headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json",
}
payload = {
    "audioConfig": {
        "audioEncoding": "MP3",
        "pitch": 0,
        "speakingRate": 1.2,
    },
    "input": {
        "text": text,
        "prompt": "Read aloud in a warm, welcoming tone.",
    },
    "voice": {
        "languageCode": "en-US",
        "modelName": "gemini-2.5-flash-lite-preview-tts",
        "name": "Aoede",
    },
}

response = requests.post(url, headers=headers, json=payload)
response.raise_for_status()
audio_content = base64.b64decode(response.json()["audioContent"])

speech_path = os.path.join(OUTPUT_DIR, "test_first_line.mp3")
with open(speech_path, "wb") as f:
    f.write(audio_content)
print(f"Speech saved: {speech_path}")

# Mix with intro music - music should be audible under speech
output_path = os.path.join(OUTPUT_DIR, "test_intro_with_music.mp3")

# Try a simpler mix: music plays, speech overlays on top
cmd = [
    "ffmpeg", "-y",
    "-i", speech_path,
    "-i", MUSIC_INTRO,
    "-filter_complex",
    # Music at full volume, speech at full volume, mixed together
    "[1:a]volume=1.0[music];"
    "[0:a]adelay=2000|2000[speech];"  # Delay speech by 2 seconds so music plays first
    "[music][speech]amix=inputs=2:duration=longest:dropout_transition=0,volume=2.0",
    "-acodec", "libmp3lame",
    "-q:a", "2",
    output_path,
]
subprocess.run(cmd, check=True, capture_output=True)
print(f"Mixed output: {output_path}")

# Get duration
result = subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
     "-of", "default=noprint_wrappers=1:nokey=1", output_path],
    capture_output=True, text=True,
)
print(f"Duration: {float(result.stdout.strip()):.1f}s")
