#!/usr/bin/env python3
"""Generate transition test between segments 1 and 2."""

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

# End of segment 1
END_SEG1 = ("ALEX", "It's a twenty-four-hundred-year-old shift. She was, um, rediscovering virtue ethics.")
# Beginning of segment 2
START_SEG2 = ("JAMIE", "Okay, virtue ethics. Give me the quick version.")

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

print("Generating end of segment 1...")
seg1_audio = generate_speech(END_SEG1[1], END_SEG1[0])
seg1_path = os.path.join(OUTPUT_DIR, "trans_seg1_end.mp3")
with open(seg1_path, "wb") as f:
    f.write(seg1_audio)
print(f"  Saved: {seg1_path}")

print("Generating start of segment 2...")
seg2_audio = generate_speech(START_SEG2[1], START_SEG2[0])
seg2_path = os.path.join(OUTPUT_DIR, "trans_seg2_start.mp3")
with open(seg2_path, "wb") as f:
    f.write(seg2_audio)
print(f"  Saved: {seg2_path}")

# Now mix them with the transition music
# Structure: seg1 -> fade out -> 1s silence -> music (5s) -> 1.5s silence -> seg2
TRANSITION_MUSIC = os.path.join(OUTPUT_DIR, "transition_music_5s.mp3")
OUTPUT = os.path.join(OUTPUT_DIR, "test_transition_sample.mp3")

print("Mixing transition...")
cmd = [
    "ffmpeg", "-y",
    "-i", seg1_path,           # 0: end of seg1
    "-i", TRANSITION_MUSIC,    # 1: transition music
    "-i", seg2_path,           # 2: start of seg2
    "-filter_complex",
    # Seg1 with fade out at end
    "[0:a]afade=t=out:st=3:d=1[seg1];"
    # Music with slight delay after seg1, louder
    "[1:a]volume=1.2,adelay=4500|4500[music];"
    # Seg2 delayed: seg1(~4s) + gap(0.5s) + music(5s) + tension gap(1.5s) = ~11s
    "[2:a]adelay=11000|11000[seg2];"
    # Mix all together
    "[seg1][music][seg2]amix=inputs=3:duration=longest:normalize=0",
    "-acodec", "libmp3lame", "-q:a", "2",
    OUTPUT
]
subprocess.run(cmd, check=True, capture_output=True)

# Get duration
result = subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
     "-of", "default=noprint_wrappers=1:nokey=1", OUTPUT],
    capture_output=True, text=True)
print(f"Created: {OUTPUT}")
print(f"Duration: {float(result.stdout.strip()):.1f}s")
