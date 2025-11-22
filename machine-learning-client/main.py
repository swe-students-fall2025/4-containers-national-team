"""Machine learning client for the Pitch Detector project.

This worker polls MongoDB for new recordings with status "pending",
estimates their pitch using the pretrained torchcrepe CNN model, and
writes the analysis results back into the same MongoDB document.
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any, Dict, Optional

import numpy as np
import torch
import torchaudio
import torchcrepe
from pymongo.collection import Collection

from db import get_db

POLL_INTERVAL_SECONDS = 5.0  # how often to check Mongo for new work


def hz_to_note(pitch_hz: float) -> str:
    """Convert a frequency in Hz to the nearest note name (e.g. A4)."""
    if pitch_hz <= 0:
        return "N/A"

    # A4 = 440 Hz, MIDI 69
    midi = 69 + 12 * np.log2(pitch_hz / 440.0)
    midi_rounded = int(round(midi))

    note_names = ["C", "C#", "D", "D#", "E", "F",
                  "F#", "G", "G#", "A", "A#", "B"]
    octave = (midi_rounded // 12) - 1
    name = note_names[midi_rounded % 12]
    return f"{name}{octave}"


def analyze_file(path: str, device: torch.device) -> Optional[Dict[str, Any]]:
    """Estimate pitch for an audio file using torchcrepe.

    Returns a dict with pitch_hz, pitch_note, confidence, method,
    or None if analysis failed.
    """
    try:
        # Load audio: shape (channels, samples)
        audio, sr = torchaudio.load(path)
    except Exception as exc:  # pylint: disable=broad-except
        print(f"[analyze_file] Failed to load {path}: {exc}")
        return None

    if audio.numel() == 0:
        print(f"[analyze_file] Empty audio file at {path}")
        return None

    # Convert to mono by averaging channels, keep shape (1, samples)
    if audio.shape[0] > 1:
        audio = torch.mean(audio, dim=0, keepdim=True)

    # Resample to 16 kHz (torchcrepe's preferred rate)
    target_sr = 16000
    if sr != target_sr:
        audio = torchaudio.functional.resample(audio, sr, target_sr)
        sr = target_sr

    # Move to device
    audio = audio.to(device)

    # Hop length controls time resolution (in samples)
    hop_length = 160  # 10 ms at 16 kHz

    # Frequency range: C1 (~32.7 Hz) to C8 (~4186 Hz)
    fmin = 32.7
    fmax = 4186.0

    # Run torchcrepe pitch + periodicity estimation
    with torch.no_grad():
        pitch, periodicity = torchcrepe.predict(
            audio,
            sr,
            hop_length,
            fmin,
            fmax,
            model="full",          # higher quality model
            batch_size=128,
            device=device,
            return_periodicity=True,
            pad=True,
        )

    # pitch & periodicity: shape (1, T)
    pitch = pitch[0].cpu().numpy()
    periodicity = periodicity[0].cpu().numpy()

    # Consider only frames where periodicity (crepe "confidence") is high
    voiced_mask = periodicity > 0.8
    voiced_pitches = pitch[voiced_mask]

    if voiced_pitches.size == 0:
        print(f"[analyze_file] No voiced/high-confidence frames in {path}")
        return None

    # Use median pitch across voiced frames
    pitch_hz = float(np.median(voiced_pitches))
    note_name = hz_to_note(pitch_hz)

    # Confidence: average periodicity over voiced frames
    confidence = float(np.clip(np.mean(periodicity[voiced_mask]), 0.0, 1.0))

    return {
        "pitch_hz": pitch_hz,
        "pitch_note": note_name,
        "confidence": confidence,
        "method": "torchcrepe_full",
    }


def process_pending_recordings(
    collection: Collection, audio_dir: str, device: torch.device
) -> None:
    """Find and analyze all recordings with status 'pending'."""
    pending = list(collection.find({"status": "pending"}))

    if not pending:
        print("[worker] No pending recordings.")
        return

    print(f"[worker] Found {len(pending)} pending recording(s).")

    for doc in pending:
        rec_id = doc["_id"]
        filename = doc.get("audio_filename")

        if not filename:
            print(f"[worker] Skipping {rec_id}: missing audio_filename.")
            continue

        path = os.path.join(audio_dir, filename)
        if not os.path.exists(path):
            print(f"[worker] Skipping {rec_id}: file not found at {path}")
            collection.update_one(
                {"_id": rec_id},
                {
                    "$set": {
                        "status": "error",
                        "error_message": f"Audio file not found at {path}",
                        "updated_at": datetime.utcnow(),
                    }
                },
            )
            continue

        analysis = analyze_file(path, device)
        if analysis is None:
            print(f"[worker] Could not estimate pitch for {rec_id}.")
            collection.update_one(
                {"_id": rec_id},
                {
                    "$set": {
                        "status": "error",
                        "error_message": "Unable to estimate pitch.",
                        "updated_at": datetime.utcnow(),
                    }
                },
            )
            continue

        collection.update_one(
            {"_id": rec_id},
            {
                "$set": {
                    "analysis": analysis,
                    "status": "done",
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        print(f"[worker] Updated recording {rec_id} with {analysis}.")


def main() -> None:
    """Entry point for the ML client worker."""
    db = get_db()
    recordings = db.recordings

    audio_dir = os.getenv("AUDIO_DIR", "../web-app/data/recordings")
    print(f"[worker] Using audio directory: {audio_dir}")

    # Use GPU if available, else CPU
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[worker] Using device: {device}")

    while True:
        process_pending_recordings(recordings, audio_dir, device)
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
