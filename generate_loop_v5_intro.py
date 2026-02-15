#!/usr/bin/env python3
"""
Generate individual voice tracks for the INTRO scene of The Loop v5.
Parses per-line prompts from the script and uses them as TTS direction.
Outputs individual MP3s + an Audacity .lof project file with relative paths.
"""

import os
import re
import time
import base64
import subprocess
import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleAuthRequest

# Configuration
SCRIPT_PATH = "/home/user/Claude_test/The_Loop_That_Isnt_There_v5.md"
OUTPUT_DIR = "/home/user/Claude_test/loop_v5_intro"
CREDENTIALS_PATH = "/home/user/Claude_test/gcp_credentials.json"
MUSIC_INTRO = "/home/user/Claude_test/intro_music_12s.mp3"

TTS_MODEL = "gemini-2.5-flash-preview-tts"

# Base voice settings (per-line prompts override the prompt field)
VOICES = {
    "ALEX": {
        "name": "Aoede",
        "language_code": "en-US",
        "speaking_rate": 1.2,
    },
    "JAMIE": {
        "name": "Algenib",
        "language_code": "en-US",
        "speaking_rate": 1.2,
    },
}

# Global pronunciation hints prepended to every per-line prompt
PRONUNCIATION = (
    "Urumau is pronounced OO-roo-mah-oo, four syllables, stress on first, "
    "Lyttelton pronounced LIT-ul-tun, "
    "Korimako pronounced KOR-ih-MAH-koh"
)


def parse_v5_intro(filepath):
    """Parse the v5 script and extract only the INTRO scene lines.

    Returns a list of dicts:
      {"type": "dialogue", "speaker": "ALEX", "prompt": "...", "text": "..."}
      {"type": "pause", "duration": 1.0}
    """
    with open(filepath, "r") as f:
        content = f.read()

    lines = content.split("\n")
    in_intro = False
    raw_lines = []

    for line in lines:
        stripped = line.strip()

        # Detect start of INTRO section
        if re.match(r"^##\s*\\\[INTRO", stripped):
            in_intro = True
            continue

        # Stop at the next section divider after INTRO
        if in_intro and re.match(r"^-{4,}$", stripped):
            break

        if in_intro:
            raw_lines.append(line)

    # Parse raw lines into structured entries
    entries = []
    current_speaker = None
    current_prompt = None
    current_text_parts = []

    for line in raw_lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Pause markers: (pause) or (pause --- 2 seconds)
        pause_match = re.match(r"^\(pause(?:\s*---\s*(\d+)\s*seconds?)?\)$", stripped)
        if pause_match:
            # Flush any pending dialogue
            if current_speaker and current_text_parts:
                entries.append({
                    "type": "dialogue",
                    "speaker": current_speaker,
                    "prompt": current_prompt,
                    "text": " ".join(current_text_parts),
                })
                current_speaker = None
                current_prompt = None
                current_text_parts = []

            duration = float(pause_match.group(1)) if pause_match.group(1) else 1.0
            entries.append({"type": "pause", "duration": duration})
            continue

        # Speaker line: SPEAKER (prompt): text
        speaker_match = re.match(
            r"^(ALEX|JAMIE)\s*\(([^)]+)\)\s*:\s*(.*)", stripped
        )
        if speaker_match:
            # Flush previous
            if current_speaker and current_text_parts:
                entries.append({
                    "type": "dialogue",
                    "speaker": current_speaker,
                    "prompt": current_prompt,
                    "text": " ".join(current_text_parts),
                })

            current_speaker = speaker_match.group(1)
            current_prompt = speaker_match.group(2).strip()
            text = speaker_match.group(3).strip()
            current_text_parts = [text] if text else []
            continue

        # Continuation line (wrapped text from the same speaker)
        if current_speaker and stripped:
            current_text_parts.append(stripped)

    # Flush final entry
    if current_speaker and current_text_parts:
        entries.append({
            "type": "dialogue",
            "speaker": current_speaker,
            "prompt": current_prompt,
            "text": " ".join(current_text_parts),
        })

    return entries


def clean_text(text):
    """Clean text for TTS — remove inline directives and normalise punctuation."""
    # Strip inline (pause) markers so they aren't spoken aloud
    text = re.sub(r"\s*\(pause\)\s*", " ", text)
    text = text.replace(" --- ", ", ")
    text = text.replace("---", ", ")
    text = text.replace("\u2014", ", ")
    text = text.replace("...", "\u2026")
    text = text.replace("LPC", "L P C")
    text = text.replace("MTB", "M T B")
    return text.strip()


def get_access_token(credentials_path):
    credentials = service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    credentials.refresh(GoogleAuthRequest())
    return credentials.token


def synthesize_speech(access_token, text, speaker, line_prompt, max_retries=8):
    """Generate audio using per-line prompt for voice direction."""
    voice_config = VOICES[speaker]

    # Build the full prompt — keep it brief to avoid prompt leakage.
    # Only append pronunciation guide for Māori words that need it.
    # Lyttelton is common English and doesn't need guidance.
    needs_pronunciation = any(
        w in text.lower() for w in ("urumau", "korimako")
    )
    if needs_pronunciation:
        full_prompt = f"{line_prompt}. ({PRONUNCIATION})"
    else:
        full_prompt = line_prompt

    url = "https://texttospeech.googleapis.com/v1beta1/text:synthesize"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "audioConfig": {
            "audioEncoding": "MP3",
            "pitch": 0,
            "speakingRate": voice_config["speaking_rate"],
        },
        "input": {
            "text": text,
            "prompt": full_prompt,
        },
        "voice": {
            "languageCode": voice_config["language_code"],
            "modelName": TTS_MODEL,
            "name": voice_config["name"],
        },
    }

    use_prompt = True
    for attempt in range(max_retries + 1):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=180)
        except requests.exceptions.Timeout:
            if attempt < max_retries:
                wait = 2 ** (attempt + 1)
                print(f"    (timeout, retrying in {wait}s...)")
                time.sleep(wait)
                continue
            raise

        if response.status_code == 200:
            break
        if response.status_code in (429, 503) and attempt < max_retries:
            wait = 2 ** (attempt + 1)
            print(f"    ({response.status_code}, retrying in {wait}s...)")
            time.sleep(wait)
            continue
        if response.status_code == 400 and use_prompt:
            print(f"    (content flagged, retrying without prompt...)")
            del payload["input"]["prompt"]
            use_prompt = False
            response = requests.post(url, headers=headers, json=payload, timeout=180)
            if response.status_code == 200:
                break
        response.raise_for_status()

    time.sleep(0.5)
    return base64.b64decode(response.json()["audioContent"])


def generate_silence(duration_seconds, output_path):
    """Generate a silent MP3 file."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
        "-t", str(duration_seconds),
        "-acodec", "libmp3lame", "-q:a", "4",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def get_mp3_duration(filepath):
    """Get duration of an MP3 file in seconds."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", filepath],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Authenticate
    print("Authenticating with Google Cloud...")
    access_token = get_access_token(CREDENTIALS_PATH)
    print(f"TTS model: {TTS_MODEL}")

    # Parse intro scene
    print(f"Parsing intro scene from: {SCRIPT_PATH}")
    entries = parse_v5_intro(SCRIPT_PATH)
    dialogue_count = sum(1 for e in entries if e["type"] == "dialogue")
    pause_count = sum(1 for e in entries if e["type"] == "pause")
    print(f"Found {dialogue_count} dialogue lines, {pause_count} pauses")

    # Copy intro music into output dir
    import shutil
    music_filename = "00_music_intro.mp3"
    music_dest = os.path.join(OUTPUT_DIR, music_filename)
    shutil.copy(MUSIC_INTRO, music_dest)
    print(f"Copied intro music -> {music_filename}")

    # Generate all voice files
    generated_files = []  # list of (filename, type) for .lof generation
    file_idx = 1

    for entry in entries:
        if entry["type"] == "pause":
            filename = f"{file_idx:02d}_pause.mp3"
            filepath = os.path.join(OUTPUT_DIR, filename)
            print(f"  {filename}: silence ({entry['duration']}s)")
            generate_silence(entry["duration"], filepath)
            generated_files.append(filename)
            file_idx += 1

        elif entry["type"] == "dialogue":
            speaker = entry["speaker"]
            filename = f"{file_idx:02d}_{speaker.lower()}.mp3"
            filepath = os.path.join(OUTPUT_DIR, filename)
            cleaned = clean_text(entry["text"])
            print(f"  {filename}: [{entry['prompt'][:30]}...] {cleaned[:40]}...")
            audio = synthesize_speech(
                access_token, cleaned, speaker, entry["prompt"]
            )
            with open(filepath, "wb") as f:
                f.write(audio)
            generated_files.append(filename)
            file_idx += 1

    # Build .lof file with relative filenames and cumulative offsets
    print("\nBuilding Audacity .lof file...")
    lof_lines = []

    # Music starts at t=0
    lof_lines.append(f'file "{music_filename}" offset 0.000')

    # Speech tracks start after a 3s music intro
    cumulative_offset = 3.0
    for filename in generated_files:
        filepath = os.path.join(OUTPUT_DIR, filename)
        duration = get_mp3_duration(filepath)
        lof_lines.append(f'file "{filename}" offset {cumulative_offset:.3f}')
        cumulative_offset += duration

    lof_path = os.path.join(OUTPUT_DIR, "loop_intro.lof")
    with open(lof_path, "w") as f:
        f.write("\n".join(lof_lines) + "\n")

    print(f"Created: loop_intro.lof ({len(lof_lines)} entries)")
    print(f"Total estimated duration: {cumulative_offset:.1f}s")

    # Print summary
    print(f"\n=== Files in {OUTPUT_DIR}/ ===")
    for fn in sorted(os.listdir(OUTPUT_DIR)):
        size = os.path.getsize(os.path.join(OUTPUT_DIR, fn))
        print(f"  {fn}  ({size/1024:.1f} KB)")

    print("\n=== Audacity Import ===")
    print("Open loop_intro.lof in Audacity (File > Open)")
    print("Each file imports as a separate track at the specified offset.")
    print("Adjust timing by dragging tracks as needed.")


if __name__ == "__main__":
    main()
