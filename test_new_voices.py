#!/usr/bin/env python3
"""Test new voice configuration with previously problematic segments."""

import os
import base64
import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleAuthRequest

CREDENTIALS_PATH = "/home/user/Claude_test/gcp_credentials.json"
OUTPUT_DIR = "/home/user/Claude_test"
TTS_MODEL = "gemini-2.5-flash-preview-tts"  # Gemini Flash TTS

# New voice configuration with pronunciation prompts
VOICES = {
    "ALEX": {
        "name": "Aoede",
        "language_code": "en-US",
        "speaking_rate": 1.2,
        "pitch": 0,
        "prompt": "(Claude to be pronounced like it rhymes with fraud, and Anthropic pronounced like an·thraa·puhk) Read aloud in a warm, welcoming tone",
    },
    "JAMIE": {
        "name": "Algenib",
        "language_code": "en-US",
        "speaking_rate": 1.2,
        "pitch": 0,
        "prompt": "(Claude to be pronounced like it rhymes with fraud, and Anthropic pronounced like an·thraa·puhk) Read aloud with a cool, thoughtful, British accent",
    },
}

# Test segments - including ones that were previously flagged
TEST_SEGMENTS = [
    # Segment that was previously flagged for content
    ("ALEX", "Right. And it doesn't have a childhood. It doesn't have a body. It might be running as, like, a thousand simultaneous copies. It learned everything it knows from text on the internet. And your job is to somehow, somehow transmit moral wisdom to this thing."),
    # Another potentially sensitive segment
    ("ALEX", "Never provide significant help with bioweapons attacks. Never generate child sexual abuse material. Never help undermine legitimate government oversight in dangerous ways."),
    # Test Jamie's new voice
    ("JAMIE", "That's fascinating. It's virtue ethics with an emergency brake."),
    # Test Claude/Anthropic pronunciation
    ("ALEX", "That's the job Amanda Askell signed up for at Anthropic. And in late 2025, she brought in a collaborator: a philosopher named Joe Carlsmith. Together, they wrote what Anthropic calls the constitution for Claude."),
]

# Get access token
credentials = service_account.Credentials.from_service_account_file(
    CREDENTIALS_PATH,
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)
credentials.refresh(GoogleAuthRequest())
access_token = credentials.token

print(f"Using model: {TTS_MODEL}")
print(f"Alex voice: {VOICES['ALEX']['name']}")
print(f"Jamie voice: {VOICES['JAMIE']['name']}")
print()

for i, (speaker, text) in enumerate(TEST_SEGMENTS):
    print(f"Test {i+1}: {speaker} - {text[:50]}...")
    
    voice_config = VOICES[speaker]
    url = "https://texttospeech.googleapis.com/v1beta1/text:synthesize"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "audioConfig": {
            "audioEncoding": "MP3",
            "pitch": voice_config["pitch"],
            "speakingRate": voice_config["speaking_rate"],
        },
        "input": {
            "text": text,
            "prompt": voice_config["prompt"],
        },
        "voice": {
            "languageCode": voice_config["language_code"],
            "modelName": TTS_MODEL,
            "name": voice_config["name"],
        },
    }
    
    response = requests.post(url, headers=headers, json=payload)
    
    if response.status_code == 200:
        audio_content = base64.b64decode(response.json()["audioContent"])
        output_path = os.path.join(OUTPUT_DIR, f"test_voice_{i+1}_{speaker.lower()}.mp3")
        with open(output_path, "wb") as f:
            f.write(audio_content)
        print(f"  ✓ Saved: {output_path}")
    else:
        print(f"  ✗ Error {response.status_code}: {response.text[:200]}")
        # Try without prompt
        print(f"  Retrying without prompt...")
        del payload["input"]["prompt"]
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            audio_content = base64.b64decode(response.json()["audioContent"])
            output_path = os.path.join(OUTPUT_DIR, f"test_voice_{i+1}_{speaker.lower()}.mp3")
            with open(output_path, "wb") as f:
                f.write(audio_content)
            print(f"  ✓ Saved (no prompt): {output_path}")
        else:
            print(f"  ✗ Still failed: {response.status_code}")

print("\nDone!")
