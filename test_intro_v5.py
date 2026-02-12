#!/usr/bin/env python3
"""Intro v5 - longer music (12s), first few dialogue lines."""

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

# First few lines from the script
LINES = [
    ("ALEX", "So Jamie, I want to tell you about, um, an impossible job."),
    ("JAMIE", "I'm listening."),
    ("ALEX", "For the first time in history, humans tried to teach something non-human how to be good. And they wrote an eighty-page document to do it."),
]

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
        except:
            import time; time.sleep(2 ** attempt)
    raise Exception("Failed")

# Generate each line
speech_files = []
for i, (speaker, text) in enumerate(LINES):
    print(f"Generating line {i+1}: {speaker}: {text[:40]}...")
    audio = generate_speech(text, speaker)
    path = os.path.join(OUTPUT_DIR, f"intro_v5_line{i+1}.mp3")
    with open(path, "wb") as f:
        f.write(audio)
    speech_files.append(path)

# Concatenate speech with small gaps
print("Concatenating speech lines...")
concat_list = os.path.join(OUTPUT_DIR, "intro_v5_concat.txt")
with open(concat_list, "w") as f:
    for i, path in enumerate(speech_files):
        f.write(f"file '{path}'\n")

speech_concat = os.path.join(OUTPUT_DIR, "intro_v5_speech.mp3")
subprocess.run([
    "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list,
    "-acodec", "libmp3lame", "-q:a", "2", speech_concat
], check=True, capture_output=True)
os.remove(concat_list)

# Get speech duration
result = subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
     "-of", "default=noprint_wrappers=1:nokey=1", speech_concat],
    capture_output=True, text=True)
speech_dur = float(result.stdout.strip())
print(f"Speech duration: {speech_dur:.2f}s")

# Mix with 12s intro music
MUSIC_PATH = os.path.join(OUTPUT_DIR, "intro_music_12s.mp3")
OUTPUT = os.path.join(OUTPUT_DIR, "test_intro_v5.mp3")

# Music plays 3s alone, then speech starts, music fades out underneath
print("Mixing with music...")
cmd = [
    "ffmpeg", "-y",
    "-i", MUSIC_PATH,       # 0: music (12s)
    "-i", speech_concat,    # 1: speech
    "-filter_complex",
    # Music: fade in 2s, fade out 4s starting at 4s (after speech begins)
    "[0:a]volume=0.8,afade=t=in:st=0:d=2,afade=t=out:st=4:d=4[music];"
    # Speech delayed by 3s
    "[1:a]adelay=3000|3000[speech];"
    # Mix together
    "[music][speech]amix=inputs=2:duration=longest:normalize=0[out]",
    "-map", "[out]",
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

# Cleanup temp files
for f in speech_files:
    os.remove(f)
os.remove(speech_concat)
