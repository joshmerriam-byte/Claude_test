#!/usr/bin/env python3
"""
Generate podcast audio using Google Cloud Text-to-Speech Neural voices.
Produces high-quality neural TTS with two distinct voices for the hosts.
"""

import os
import re
import subprocess
from google.cloud import texttospeech_v1

# Configuration
SCRIPT_PATH = "/home/user/Claude_test/claude_constitution_podcast_script.md"
OUTPUT_DIR = "/home/user/Claude_test/audio"
FINAL_OUTPUT = "/home/user/Claude_test/claude_constitution_podcast.mp3"
CREDENTIALS_PATH = "/home/user/Claude_test/gcp_credentials.json"

# Voice configurations - Neural2 voices for natural sound
VOICES = {
    "ALEX": {
        "name": "en-US-Neural2-D",  # American male
        "language_code": "en-US",
        "speaking_rate": 1.0,
        "pitch": 0.0,
    },
    "JAMIE": {
        "name": "en-GB-Neural2-B",  # British male
        "language_code": "en-GB",
        "speaking_rate": 1.0,
        "pitch": 0.0,
    },
}

# Pause durations (in seconds)
PAUSE_BETWEEN_LINES = 0.3
PAUSE_BETWEEN_SEGMENTS = 0.8
PAUSE_AFTER_SECTION_HEADER = 0.5


def parse_script(filepath):
    """Parse the markdown script into a sequence of (speaker, text) tuples
    and structural markers."""
    with open(filepath, "r") as f:
        content = f.read()

    lines = content.split("\n")
    in_dialogue = False
    dialogue_lines = []

    for line in lines:
        stripped = line.strip()

        # Start capturing after first "---"
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
    """Clean markdown formatting for TTS."""
    # Remove markdown bold/italic
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)

    # Replace special punctuation
    text = text.replace("...", "...")
    text = text.replace(" -- ", ", ")
    text = text.replace("--", ", ")
    text = text.replace('"', '"').replace('"', '"')
    text = text.replace("'", "'").replace("'", "'")

    # Handle abbreviations
    text = text.replace("PhD", "P H D")
    text = text.replace("NYU", "N Y U")
    text = text.replace("AI", "A I")

    # Clean up remaining markdown
    text = re.sub(r'\[([^\]]+)\]', r'\1', text)

    return text.strip()


def synthesize_speech(client, text, speaker):
    """Generate audio for text using the specified speaker's voice."""
    voice_config = VOICES[speaker]

    synthesis_input = texttospeech_v1.SynthesisInput(text=text)

    voice = texttospeech_v1.VoiceSelectionParams(
        language_code=voice_config["language_code"],
        name=voice_config["name"]
    )

    audio_config = texttospeech_v1.AudioConfig(
        audio_encoding=texttospeech_v1.AudioEncoding.MP3,
        speaking_rate=voice_config["speaking_rate"],
        pitch=voice_config["pitch"]
    )

    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config
    )

    return response.audio_content


def generate_silence(duration_seconds, output_path):
    """Generate a silent MP3 file of the given duration."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"anullsrc=r=24000:cl=mono",
        "-t", str(duration_seconds),
        "-acodec", "libmp3lame",
        "-q:a", "4",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def concat_audio_files(audio_files, output_path):
    """Concatenate multiple audio files into a single file using ffmpeg."""
    list_path = os.path.join(OUTPUT_DIR, "concat_list.txt")
    with open(list_path, "w") as f:
        for audio_file in audio_files:
            f.write(f"file '{audio_file}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_path,
        "-acodec", "libmp3lame",
        "-q:a", "2",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)

    os.remove(list_path)


def main():
    # Set credentials
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CREDENTIALS_PATH

    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Initialize client with REST transport
    print("Initializing Google Cloud TTS client...")
    client = texttospeech_v1.TextToSpeechClient(transport='rest')

    # Parse script
    print(f"Parsing script: {SCRIPT_PATH}")
    segments = parse_script(SCRIPT_PATH)
    dialogue_count = sum(1 for s in segments if s[0] == "dialogue")
    print(f"Found {len(segments)} segments ({dialogue_count} dialogue lines)")

    # Generate audio for each segment
    audio_files = []
    segment_idx = 0

    for seg_type, speaker, text in segments:
        if seg_type == "section":
            # Add pause for section breaks
            pause_path = os.path.join(OUTPUT_DIR, f"seg_{segment_idx:04d}_section_pause.mp3")
            generate_silence(PAUSE_AFTER_SECTION_HEADER, pause_path)
            audio_files.append(pause_path)
            segment_idx += 1
            print(f"  [Section: {speaker}]")

        elif seg_type == "pause":
            pause_path = os.path.join(OUTPUT_DIR, f"seg_{segment_idx:04d}_pause.mp3")
            generate_silence(PAUSE_BETWEEN_SEGMENTS, pause_path)
            audio_files.append(pause_path)
            segment_idx += 1

        elif seg_type == "dialogue":
            cleaned = clean_text_for_tts(text)
            if not cleaned:
                continue

            # Generate speech
            print(f"  Generating: {speaker}: {cleaned[:50]}...")
            audio_content = synthesize_speech(client, cleaned, speaker)

            # Save audio
            audio_path = os.path.join(OUTPUT_DIR, f"seg_{segment_idx:04d}_{speaker.lower()}.mp3")
            with open(audio_path, "wb") as f:
                f.write(audio_content)
            audio_files.append(audio_path)
            segment_idx += 1

            # Add inter-line pause
            pause_path = os.path.join(OUTPUT_DIR, f"seg_{segment_idx:04d}_gap.mp3")
            generate_silence(PAUSE_BETWEEN_LINES, pause_path)
            audio_files.append(pause_path)
            segment_idx += 1

    if not audio_files:
        print("ERROR: No audio segments generated!")
        return

    # Concatenate all audio
    print(f"\nConcatenating {len(audio_files)} audio segments...")
    concat_audio_files(audio_files, FINAL_OUTPUT)

    # Get duration
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

    # Report file size
    size_mb = os.path.getsize(FINAL_OUTPUT) / (1024 * 1024)
    print(f"File size: {size_mb:.1f} MB")
    print(f"\nDone! Output: {FINAL_OUTPUT}")

    # Cleanup individual segment files
    print("\nCleaning up temporary segment files...")
    for audio_file in audio_files:
        if os.path.exists(audio_file):
            os.remove(audio_file)

    print("Audio generation complete!")


if __name__ == "__main__":
    main()
