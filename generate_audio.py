#!/usr/bin/env python3
"""
Generate podcast audio from the Moltbook podcast script.
Uses espeak-ng for TTS with two distinct voices, ffmpeg for assembly.
"""

import subprocess
import os
import re
import tempfile
import shutil

SCRIPT_PATH = "/home/user/Claude_test/moltbook_podcast_script.md"
OUTPUT_DIR = "/home/user/Claude_test/audio"
FINAL_OUTPUT = "/home/user/Claude_test/moltbook_podcast.mp3"

# Voice configurations for the two hosts
VOICES = {
    "ALEX": {
        "voice": "en-us",
        "speed": "255",   # words per minute
        "pitch": "40",    # pitch adjustment
        "amplitude": "90",
    },
    "JAMIE": {
        "voice": "en-gb",
        "speed": "260",
        "pitch": "55",
        "amplitude": "90",
    },
}

# Pause durations (in seconds)
PAUSE_BETWEEN_LINES = 0.15
PAUSE_BETWEEN_SEGMENTS = 0.6
PAUSE_AFTER_SECTION_HEADER = 0.4


def parse_script(filepath):
    """Parse the markdown script into a sequence of (speaker, text) tuples
    and structural markers."""
    with open(filepath, "r") as f:
        content = f.read()

    # Extract only the dialogue portion (between first --- and ## Sources)
    lines = content.split("\n")
    in_dialogue = False
    dialogue_lines = []

    for line in lines:
        stripped = line.strip()

        # Start capturing after first "**[INTRO]**" or "---"
        if stripped == "---" and not in_dialogue:
            in_dialogue = True
            continue

        # Stop at Sources or Production Notes
        if stripped.startswith("## Sources") or stripped.startswith("## Production"):
            break

        if in_dialogue:
            dialogue_lines.append(line)

    # Parse dialogue lines into segments
    segments = []
    current_speaker = None
    current_text = []

    for line in dialogue_lines:
        stripped = line.strip()

        # Section headers like **[SEGMENT 1: ...]**
        if stripped.startswith("**[") and stripped.endswith("]**"):
            # Flush current text
            if current_speaker and current_text:
                segments.append(("dialogue", current_speaker, " ".join(current_text)))
                current_text = []
                current_speaker = None
            section_name = stripped.strip("*[]")
            segments.append(("section", section_name, ""))
            continue

        # Segment dividers
        if stripped == "---":
            if current_speaker and current_text:
                segments.append(("dialogue", current_speaker, " ".join(current_text)))
                current_text = []
                current_speaker = None
            segments.append(("pause", "", ""))
            continue

        # Speaker lines: **ALEX:** or **JAMIE:**
        speaker_match = re.match(r"\*\*(ALEX|JAMIE):\*\*\s*(.*)", stripped)
        if speaker_match:
            # Flush previous speaker
            if current_speaker and current_text:
                segments.append(("dialogue", current_speaker, " ".join(current_text)))
                current_text = []

            current_speaker = speaker_match.group(1)
            text = speaker_match.group(2).strip()
            if text:
                current_text.append(text)
            continue

        # Continuation of current speaker's text
        if current_speaker and stripped:
            current_text.append(stripped)

    # Flush final segment
    if current_speaker and current_text:
        segments.append(("dialogue", current_speaker, " ".join(current_text)))

    return segments


def clean_text_for_tts(text):
    """Clean markdown formatting and special characters for TTS."""
    # Remove markdown bold/italic
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)

    # Replace special punctuation
    text = text.replace("...", ". . .")
    text = text.replace(" -- ", ", ")
    text = text.replace("--", ", ")
    text = text.replace('"', '"').replace('"', '"')
    text = text.replace("'", "'").replace("'", "'")

    # Handle some abbreviations for better pronunciation
    text = text.replace("u/sam_altman", "user sam altman")
    text = text.replace("u/sam underscore altman", "user sam altman")
    text = text.replace("sam_altman", "sam altman")
    text = text.replace("@vicroy187", "at vicroy one eighty seven")
    text = text.replace("vicroy187", "vicroy one eighty seven")
    text = text.replace("SOUL.md", "soul dot M D")
    text = text.replace("Soul.md", "soul dot M D")
    text = text.replace("SSH", "S S H")
    text = text.replace("$MOLT", "MOLT token")
    text = text.replace("m/governance", "M governance")
    text = text.replace("m/agentlegaladvice", "M agent legal advice")
    text = text.replace("QA", "Q A")
    text = text.replace("API", "A P I")
    text = text.replace("WTF", "W T F")

    # Clean up remaining markdown artifacts
    text = re.sub(r'\[([^\]]+)\]', r'\1', text)

    return text.strip()


def generate_wav(text, speaker, output_path):
    """Generate a WAV file for the given text with the speaker's voice."""
    voice_config = VOICES[speaker]
    cmd = [
        "espeak-ng",
        "-v", voice_config["voice"],
        "-s", voice_config["speed"],
        "-p", voice_config["pitch"],
        "-a", voice_config["amplitude"],
        "-w", output_path,
        text,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def generate_silence(duration_seconds, output_path):
    """Generate a silent WAV file of the given duration."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"anullsrc=r=22050:cl=mono",
        "-t", str(duration_seconds),
        "-acodec", "pcm_s16le",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def concat_wavs(wav_files, output_path):
    """Concatenate multiple WAV files into a single file using ffmpeg."""
    # Create a concat file list
    list_path = os.path.join(OUTPUT_DIR, "concat_list.txt")
    with open(list_path, "w") as f:
        for wav in wav_files:
            f.write(f"file '{wav}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_path,
        "-acodec", "pcm_s16le",
        "-ar", "22050",
        "-ac", "1",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def wav_to_mp3(wav_path, mp3_path):
    """Convert WAV to MP3 with reasonable quality."""
    cmd = [
        "ffmpeg", "-y",
        "-i", wav_path,
        "-codec:a", "libmp3lame",
        "-qscale:a", "4",
        "-ar", "44100",
        mp3_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def main():
    # Setup
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("Parsing podcast script...")
    segments = parse_script(SCRIPT_PATH)
    print(f"Found {len(segments)} segments")

    # Count dialogue segments
    dialogue_count = sum(1 for s in segments if s[0] == "dialogue")
    print(f"  - {dialogue_count} dialogue lines")

    # Generate individual WAV files
    wav_files = []
    segment_idx = 0

    for seg_type, speaker, text in segments:
        if seg_type == "section":
            # Add a longer pause for section breaks
            pause_path = os.path.join(OUTPUT_DIR, f"seg_{segment_idx:04d}_section_pause.wav")
            generate_silence(PAUSE_AFTER_SECTION_HEADER, pause_path)
            wav_files.append(pause_path)
            segment_idx += 1
            print(f"  [Section: {speaker}]")

        elif seg_type == "pause":
            pause_path = os.path.join(OUTPUT_DIR, f"seg_{segment_idx:04d}_pause.wav")
            generate_silence(PAUSE_BETWEEN_SEGMENTS, pause_path)
            wav_files.append(pause_path)
            segment_idx += 1

        elif seg_type == "dialogue":
            cleaned = clean_text_for_tts(text)
            if not cleaned:
                continue

            # Generate the dialogue audio
            wav_path = os.path.join(OUTPUT_DIR, f"seg_{segment_idx:04d}_{speaker.lower()}.wav")
            print(f"  Generating: {speaker}: {cleaned[:60]}...")
            generate_wav(cleaned, speaker, wav_path)
            wav_files.append(wav_path)
            segment_idx += 1

            # Add inter-line pause
            pause_path = os.path.join(OUTPUT_DIR, f"seg_{segment_idx:04d}_gap.wav")
            generate_silence(PAUSE_BETWEEN_LINES, pause_path)
            wav_files.append(pause_path)
            segment_idx += 1

    if not wav_files:
        print("ERROR: No audio segments generated!")
        return

    print(f"\nConcatenating {len(wav_files)} audio segments...")
    combined_wav = os.path.join(OUTPUT_DIR, "combined.wav")
    concat_wavs(wav_files, combined_wav)

    print(f"Converting to MP3...")
    wav_to_mp3(combined_wav, FINAL_OUTPUT)

    # Report file size and duration
    size_mb = os.path.getsize(FINAL_OUTPUT) / (1024 * 1024)
    print(f"\nDone! Output: {FINAL_OUTPUT}")
    print(f"File size: {size_mb:.1f} MB")

    # Get duration via ffprobe
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", FINAL_OUTPUT],
            capture_output=True, text=True,
        )
        duration = float(result.stdout.strip())
        minutes = int(duration // 60)
        seconds = int(duration % 60)
        print(f"Duration: {minutes}m {seconds}s")
    except Exception:
        pass

    # Cleanup individual segment files (keep the final outputs)
    print("\nCleaning up temporary segment files...")
    for wav in wav_files:
        if os.path.exists(wav):
            os.remove(wav)
    concat_list = os.path.join(OUTPUT_DIR, "concat_list.txt")
    if os.path.exists(concat_list):
        os.remove(concat_list)
    if os.path.exists(combined_wav):
        os.remove(combined_wav)

    print("Audio generation complete!")


if __name__ == "__main__":
    main()
