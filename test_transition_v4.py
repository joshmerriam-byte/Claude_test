#!/usr/bin/env python3
"""Transition v4 - longer fades, 0.5s later start, 1.0s tension gap."""

import os
import subprocess

OUTPUT_DIR = "/home/user/Claude_test"
ALEX_PATH = os.path.join(OUTPUT_DIR, "trans_v3_alex.mp3")  # Reuse existing
JAMIE_PATH = os.path.join(OUTPUT_DIR, "trans_v3_jamie.mp3")
MUSIC_PATH = os.path.join(OUTPUT_DIR, "transition_raw.mp3")
OUTPUT = os.path.join(OUTPUT_DIR, "test_transition_v4.mp3")

# Get Alex duration
result = subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
     "-of", "default=noprint_wrappers=1:nokey=1", ALEX_PATH],
    capture_output=True, text=True)
alex_dur = float(result.stdout.strip())
print(f"Alex duration: {alex_dur:.2f}s")

# Music starts 1.5s before Alex ends (was 2s, now 0.5s later)
music_start_time = max(0, alex_dur - 1.5)
music_start_ms = int(music_start_time * 1000)

# Jamie starts: after Alex ends + music (5s) + 1.0s tension (reduced from 1.5s)
jamie_start_ms = int((alex_dur + 5 + 1.0) * 1000)

print(f"Music starts at: {music_start_ms}ms (overlapping last 1.5s of Alex)")
print(f"Jamie starts at: {jamie_start_ms}ms (1.0s tension gap)")

# Mix with longer fades: fade in 2s (was 1s), fade out 2s (was 1s)
cmd = [
    "ffmpeg", "-y",
    "-i", ALEX_PATH,
    "-i", MUSIC_PATH,
    "-i", JAMIE_PATH,
    "-filter_complex",
    f"[0:a]apad=pad_dur=7[alex];"
    f"[1:a]afade=t=in:st=0:d=2,afade=t=out:st=3:d=2,adelay={music_start_ms}|{music_start_ms}[music];"
    f"[2:a]adelay={jamie_start_ms}|{jamie_start_ms}[jamie];"
    f"[alex][music][jamie]amix=inputs=3:duration=longest:weights=1 0.8 1:normalize=0",
    "-acodec", "libmp3lame", "-q:a", "2",
    OUTPUT
]

print("Mixing with longer fades...")
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
