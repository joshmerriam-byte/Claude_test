#!/usr/bin/env python3
"""Test improved intro music mixing."""

import subprocess

SPEECH = "/home/user/Claude_test/test_first_line.mp3"
MUSIC_INTRO = "/home/user/Claude_test/music_intro_v2.mp3"
OUTPUT = "/home/user/Claude_test/test_intro_v2.mp3"

# Use the improved mixing approach
cmd = [
    "ffmpeg", "-y",
    "-i", SPEECH,
    "-i", MUSIC_INTRO,
    "-filter_complex",
    # Intro music: volume up, fade in quickly, fade out as speech plays
    "[1:a]volume=1.5,afade=t=in:st=0:d=2,afade=t=out:st=8:d=5[intro];"
    # Speech: delay by 3 seconds so music plays first
    "[0:a]adelay=3000|3000[speech_delayed];"
    # Mix with weights - normalize=0 prevents volume reduction
    "[speech_delayed][intro]amix=inputs=2:duration=longest:weights=1 0.6:normalize=0[final]",
    "-map", "[final]",
    "-acodec", "libmp3lame",
    "-q:a", "2",
    OUTPUT,
]
result = subprocess.run(cmd, capture_output=True, text=True)
if result.returncode != 0:
    print(f"Error: {result.stderr}")
else:
    # Get duration
    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", OUTPUT],
        capture_output=True, text=True
    )
    print(f"Created: {OUTPUT}")
    print(f"Duration: {float(dur.stdout.strip()):.1f}s")
