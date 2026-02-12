#!/usr/bin/env python3
"""Intro test v4 - fix duplicate speech, ensure music plays."""

import os
import subprocess

OUTPUT_DIR = "/home/user/Claude_test"
SPEECH_PATH = os.path.join(OUTPUT_DIR, "intro_v3_speech.mp3")  # Reuse existing
MUSIC_PATH = os.path.join(OUTPUT_DIR, "intro_music_8s.mp3")
OUTPUT = os.path.join(OUTPUT_DIR, "test_intro_v4.mp3")

# Get speech duration
result = subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
     "-of", "default=noprint_wrappers=1:nokey=1", SPEECH_PATH],
    capture_output=True, text=True)
speech_dur = float(result.stdout.strip())
print(f"Speech duration: {speech_dur:.2f}s")

# Structure: 3s music alone, then speech starts with music fading underneath
# Music: fade in 2s, then fade out longer (3s) starting when speech begins
print("Mixing intro...")
cmd = [
    "ffmpeg", "-y",
    "-i", MUSIC_PATH,      # 0: music (8s)
    "-i", SPEECH_PATH,     # 1: speech
    "-filter_complex",
    # Music at good volume, fade in 2s, fade out 3s starting at 3s (when speech begins)
    "[0:a]volume=0.8,afade=t=in:st=0:d=2,afade=t=out:st=3:d=3[music];"
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
