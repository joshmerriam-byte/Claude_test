#!/usr/bin/env python3
"""
Generate the full podcast episode for The Loop v5.
- Parses ALL acts from the script
- Generates TTS for Acts I–VI (intro reuses existing clips)
- Concatenates each act's clips into a single act MP3
- Builds a master .LOF file where each entry is one act
"""

import os
import re
import time
import base64
import shutil
import subprocess
import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleAuthRequest

# Configuration
SCRIPT_PATH = "/home/user/Claude_test/The_Loop_That_Isnt_There_v5.md"
OUTPUT_DIR = "/home/user/Claude_test/loop_v5_full"
CREDENTIALS_PATH = "/home/user/Claude_test/gcp_credentials.json"
INTRO_DIR = "/home/user/Claude_test/loop_v5_intro"

TTS_MODEL = "gemini-2.5-flash-preview-tts"

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

# Pronunciation reference (not sent to TTS — kept here for documentation).
# Lyttelton: "little-ton" (LIT-ul-ton)
# Urumau: 3 syllables, no stress emphasis, last syllable rhymes with toe/Moe — "oo-roo-moe"
# Korimako: KOR-ih-MAH-koh

# Section definitions in script order
SECTIONS = [
    {"tag": "INTRO", "slug": "intro", "label": "Intro"},
    {"tag": "ACT I", "slug": "act_01_the_missing_piece", "label": "Act I — The Missing Piece"},
    {"tag": "ACT II", "slug": "act_02_the_no", "label": "Act II — The No"},
    {"tag": "ACT III", "slug": "act_03_the_line_between", "label": "Act III — The Line Between"},
    {"tag": "ACT IV", "slug": "act_04_time", "label": "Act IV — Time"},
    {"tag": "ACT V", "slug": "act_05_small_goods", "label": "Act V — Small Goods"},
    {"tag": "ACT VI", "slug": "act_06_accepting_no", "label": "Act VI — Accepting No"},
]

# Small gap (seconds) inserted between consecutive dialogue lines
INTER_LINE_GAP = 0.3


def parse_all_sections(filepath):
    """Parse the v5 script and extract all sections.

    Returns a dict mapping section tag -> list of entries:
      {"type": "dialogue", "speaker": "ALEX", "prompt": "...", "text": "..."}
      {"type": "pause", "duration": 1.0}
    """
    with open(filepath, "r") as f:
        content = f.read()

    lines = content.split("\n")

    # Find section boundaries
    section_starts = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        m = re.match(r"^##\s*\\\[(.*?)(?:\s*--\s*.*)?\\\]", stripped)
        if m:
            tag = m.group(1).strip()
            section_starts.append((i, tag))

    # Find divider lines
    dividers = set()
    for i, line in enumerate(lines):
        if re.match(r"^-{4,}$", line.strip()):
            dividers.add(i)

    # Extract raw lines per section
    sections_raw = {}
    for idx, (start_line, tag) in enumerate(section_starts):
        raw = []
        for i in range(start_line + 1, len(lines)):
            if i in dividers and i > start_line:
                # Check if this divider is before the next section start
                if idx + 1 < len(section_starts) and i < section_starts[idx + 1][0]:
                    break
                elif idx + 1 >= len(section_starts):
                    break
            if i in dividers:
                continue
            # Stop if we hit the next section header
            if any(i == s for s, _ in section_starts[idx + 1:]):
                break
            raw.append(lines[i])
        sections_raw[tag] = raw

    # Parse each section's raw lines into entries
    result = {}
    for tag, raw_lines in sections_raw.items():
        result[tag] = _parse_lines(raw_lines)

    return result


def _parse_lines(raw_lines):
    """Parse raw text lines into structured dialogue/pause entries."""
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

        # Continuation line
        if current_speaker and stripped:
            current_text_parts.append(stripped)

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


def concatenate_mp3s(file_list, output_path):
    """Concatenate a list of MP3 files into a single MP3 using ffmpeg."""
    if not file_list:
        return

    # Build ffmpeg concat file
    concat_list = output_path + ".concat.txt"
    with open(concat_list, "w") as f:
        for fp in file_list:
            f.write(f"file '{fp}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_list,
        "-acodec", "libmp3lame", "-q:a", "2",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    os.remove(concat_list)


def compile_intro_act(output_path):
    """Concatenate existing intro clips (dialogue only, no music) into one act file."""
    print("\n=== Compiling Intro from existing clips ===")

    # Gather intro clips in order (skip 00_music_intro.mp3)
    intro_files = sorted([
        f for f in os.listdir(INTRO_DIR)
        if f.endswith(".mp3") and not f.startswith("00_")
    ])

    clip_paths = [os.path.join(INTRO_DIR, f) for f in intro_files]
    print(f"  Concatenating {len(clip_paths)} intro clips...")

    concatenate_mp3s(clip_paths, output_path)
    dur = get_mp3_duration(output_path)
    print(f"  -> {os.path.basename(output_path)} ({dur:.1f}s)")
    return dur


def generate_act(act_tag, act_slug, entries, access_token, output_path):
    """Generate TTS for an act's dialogue, concatenate into one act file."""
    print(f"\n=== Generating {act_tag} ({len(entries)} entries) ===")

    act_tmp_dir = os.path.join(OUTPUT_DIR, f"_tmp_{act_slug}")
    os.makedirs(act_tmp_dir, exist_ok=True)

    # Generate silence file for inter-line gaps
    gap_path = os.path.join(act_tmp_dir, "gap.mp3")
    generate_silence(INTER_LINE_GAP, gap_path)

    clip_paths = []
    file_idx = 0

    for entry in entries:
        if entry["type"] == "pause":
            filename = f"{file_idx:02d}_pause.mp3"
            filepath = os.path.join(act_tmp_dir, filename)
            print(f"  {filename}: silence ({entry['duration']}s)")
            generate_silence(entry["duration"], filepath)
            clip_paths.append(filepath)
            file_idx += 1

        elif entry["type"] == "dialogue":
            # Insert gap before this line (except the very first)
            if clip_paths:
                clip_paths.append(gap_path)

            speaker = entry["speaker"]
            filename = f"{file_idx:02d}_{speaker.lower()}.mp3"
            filepath = os.path.join(act_tmp_dir, filename)
            cleaned = clean_text(entry["text"])
            prompt_preview = entry["prompt"][:30]
            text_preview = cleaned[:40]
            print(f"  {filename}: [{prompt_preview}...] {text_preview}...")

            audio = synthesize_speech(
                access_token, cleaned, speaker, entry["prompt"]
            )
            with open(filepath, "wb") as f:
                f.write(audio)
            clip_paths.append(filepath)
            file_idx += 1

    # Concatenate all clips into one act file
    print(f"  Concatenating {file_idx} clips...")
    concatenate_mp3s(clip_paths, output_path)
    dur = get_mp3_duration(output_path)
    print(f"  -> {os.path.basename(output_path)} ({dur:.1f}s)")

    # Clean up temp dir
    shutil.rmtree(act_tmp_dir)

    return dur


def build_master_lof(act_files_with_durations, lof_path):
    """Build an Audacity .lof file with one entry per act, sequential offsets."""
    print("\n=== Building master .LOF ===")

    lof_lines = []
    cumulative_offset = 0.0

    for filename, duration in act_files_with_durations:
        lof_lines.append(f'file "{filename}" offset {cumulative_offset:.3f}')
        cumulative_offset += duration

    with open(lof_path, "w") as f:
        f.write("\n".join(lof_lines) + "\n")

    print(f"Created: {os.path.basename(lof_path)} ({len(lof_lines)} entries)")
    print(f"Total episode duration: {cumulative_offset:.1f}s ({cumulative_offset/60:.1f} min)")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Authenticate
    print("Authenticating with Google Cloud...")
    access_token = get_access_token(CREDENTIALS_PATH)
    print(f"TTS model: {TTS_MODEL}")

    # Parse all sections
    print(f"Parsing script: {SCRIPT_PATH}")
    all_sections = parse_all_sections(SCRIPT_PATH)

    for tag, entries in all_sections.items():
        dialogue_count = sum(1 for e in entries if e["type"] == "dialogue")
        pause_count = sum(1 for e in entries if e["type"] == "pause")
        print(f"  {tag}: {dialogue_count} dialogue, {pause_count} pauses")

    # Process each act
    act_results = []  # list of (filename, duration)

    for section in SECTIONS:
        tag = section["tag"]
        slug = section["slug"]
        output_file = f"{slug}.mp3"
        output_path = os.path.join(OUTPUT_DIR, output_file)

        if tag == "INTRO":
            dur = compile_intro_act(output_path)
        else:
            entries = all_sections.get(tag, [])
            if not entries:
                print(f"\nWARNING: No entries found for {tag}, skipping.")
                continue
            dur = generate_act(tag, slug, entries, access_token, output_path)

        act_results.append((output_file, dur))

    # Build master .lof
    lof_path = os.path.join(OUTPUT_DIR, "the_loop_full.lof")
    build_master_lof(act_results, lof_path)

    # Summary
    print(f"\n=== Files in {OUTPUT_DIR}/ ===")
    for fn in sorted(os.listdir(OUTPUT_DIR)):
        fp = os.path.join(OUTPUT_DIR, fn)
        if os.path.isfile(fp):
            size = os.path.getsize(fp)
            print(f"  {fn}  ({size/1024:.1f} KB)")

    print("\n=== Audacity Import ===")
    print("Open the_loop_full.lof in Audacity (File > Open)")
    print("Each act imports as a separate track at sequential offsets.")


if __name__ == "__main__":
    main()
