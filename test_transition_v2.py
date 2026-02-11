#!/usr/bin/env python3
"""Generate transition test v2 - fix cutoff and louder music."""

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

# Split the Alex line to avoid cutoff
SEG1_PART1 = ("ALEX", "It's a twenty-four-hundred-year-old shift.")
SEG1_PART2 = ("ALEX", "She was, um, rediscovering virtue ethics.")
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

print("Generating seg1 part 1...")
part1 = generate_speech(SEG1_PART1[1], SEG1_PART1[0])
with open(os.path.join(OUTPUT_DIR, "trans_v2_part1.mp3"), "wb") as f:
    f.write(part1)

print("Generating seg1 part 2...")
part2 = generate_speech(SEG1_PART2[1], SEG1_PART2[0])
with open(os.path.join(OUTPUT_DIR, "trans_v2_part2.mp3"), "wb") as f:
    f.write(part2)

print("Generating seg2 start...")
seg2 = generate_speech(START_SEG2[1], START_SEG2[0])
with open(os.path.join(OUTPUT_DIR, "trans_v2_seg2.mp3"), "wb") as f:
    f.write(seg2)

# Concatenate part1 and part2 with small gap
print("Concatenating seg1...")
subprocess.run([
    "ffmpeg", "-y",
    "-i", os.path.join(OUTPUT_DIR, "trans_v2_part1.mp3"),
    "-i", os.path.join(OUTPUT_DIR, "trans_v2_part2.mp3"),
    "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1,afade=t=out:st=4:d=1[out]",
    "-map", "[out]",
    "-acodec", "libmp3lame", "-q:a", "2",
    os.path.join(OUTPUT_DIR, "trans_v2_seg1_full.mp3")
], check=True, capture_output=True)

# Get seg1 duration
result = subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
     "-of", "default=noprint_wrappers=1:nokey=1", 
     os.path.join(OUTPUT_DIR, "trans_v2_seg1_full.mp3")],
    capture_output=True, text=True)
seg1_dur = float(result.stdout.strip())
print(f"Seg1 duration: {seg1_dur:.1f}s")

# Mix with LOUD music
# Structure: seg1 ends -> 0.5s -> LOUD music (5s) -> 1.5s silence -> seg2
TRANSITION_MUSIC = os.path.join(OUTPUT_DIR, "transition_music_5s.mp3")
OUTPUT = os.path.join(OUTPUT_DIR, "test_transition_v2.mp3")

music_start = int((seg1_dur + 0.3) * 1000)  # Start music 0.3s after seg1 ends
seg2_start = int((seg1_dur + 0.3 + 5 + 1.5) * 1000)  # seg1 + gap + music + tension

print(f"Music starts at: {music_start}ms")
print(f"Seg2 starts at: {seg2_start}ms")

print("Mixing with LOUD music...")
cmd = [
    "ffmpeg", "-y",
    "-i", os.path.join(OUTPUT_DIR, "trans_v2_seg1_full.mp3"),  # 0: seg1
    "-i", TRANSITION_MUSIC,                                     # 1: music
    "-i", os.path.join(OUTPUT_DIR, "trans_v2_seg2.mp3"),       # 2: seg2
    "-filter_complex",
    f"[0:a]apad=pad_dur=0.5[seg1pad];"
    f"[1:a]volume=3.0,adelay={music_start}|{music_start}[music];"  # LOUD music
    f"[2:a]adelay={seg2_start}|{seg2_start}[seg2];"
    f"[seg1pad][music][seg2]amix=inputs=3:duration=longest:normalize=0",
    "-acodec", "libmp3lame", "-q:a", "2",
    OUTPUT
]
subprocess.run(cmd, check=True, capture_output=True)

# Get final duration
result = subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
     "-of", "default=noprint_wrappers=1:nokey=1", OUTPUT],
    capture_output=True, text=True)
print(f"Created: {OUTPUT}")
print(f"Duration: {float(result.stdout.strip()):.1f}s")
