"""Background ML worker that analyzes recordings and writes pitch info to MongoDB."""

from __future__ import annotations

import math
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import soundfile as sf
import torch
import torchcrepe

from db import get_db

POLL_INTERVAL_SECONDS = 5.0


def get_audio_dir() -> Path:
    """Return the directory where the web app saves recordings.
    """
    env_dir = os.getenv("AUDIO_DIR")
    if env_dir:
        path = Path(env_dir).resolve()
    else:
        base = Path(__file__).resolve().parent
        path = (base / ".." / "web-app" / "data" / "recordings").resolve()

    path.mkdir(parents=True, exist_ok=True)
    return path


def convert_to_wav(input_path: Path, output_dir: Path) -> Path:
    """Use ffmpeg to convert any audio file to mono 16 kHz WAV."""
    output_dir.mkdir(parents=True, exist_ok=True)
    wav_path = output_dir / f"{input_path.stem}.wav"

    cmd = [
        "ffmpeg",
        "-y",  # overwrite
        "-loglevel",
        "error",  # only show errors
        "-i",
        str(input_path),
        "-ac",
        "1",  # mono
        "-ar",
        "16000",  # 16 kHz
        str(wav_path),
    ]
    # If ffmpeg fails, this will raise CalledProcessError so we see it.
    subprocess.run(cmd, check=True)
    return wav_path


def hz_to_note(pitch_hz: float) -> str:
    """Convert a frequency in Hz to a note name like 'A4'."""
    if pitch_hz <= 0:
        return "N/A"

    midi = 69 + 12 * math.log2(pitch_hz / 440.0)
    midi_rounded = int(round(midi))

    note_names = [
        "C",
        "C#",
        "D",
        "D#",
        "E",
        "F",
        "F#",
        "G",
        "G#",
        "A",
        "A#",
        "B",
    ]
    note_index = midi_rounded % 12
    octave = midi_rounded // 12 - 1

    return f"{note_names[note_index]}{octave}"


def estimate_pitch(
    waveform: torch.Tensor, sample_rate: int
) -> Optional[Tuple[float, float]]:
    """Estimate a single pitch (Hz) and confidence using torchcrepe."""
    if waveform.dim() == 2 and waveform.size(0) > 1:
        waveform = waveform.mean(dim=0, keepdim=True)
    if waveform.dim() == 1:
        waveform = waveform.unsqueeze(0)

    hop_length = sample_rate // 100

    device = torch.device("cpu")
    waveform = waveform.to(device)

    with torch.no_grad():
        pitch, periodicity = torchcrepe.predict(
            waveform,
            sample_rate,
            hop_length,
            fmin=50.0,
            fmax=800.0,
            model="tiny",
            batch_size=1024,
            device=device,
            return_periodicity=True,
        )

        pitch = torchcrepe.filter.median(pitch, 3)
        periodicity = torchcrepe.filter.median(periodicity, 3)
        pitch[periodicity < 0.1] = float("nan")

    valid = pitch[~torch.isnan(pitch)]
    if valid.numel() == 0:
        return None

    pitch_hz = float(valid.mean().item())
    confidence = float(periodicity.mean().item())
    return pitch_hz, confidence


def analyze_recording(recording: dict, audio_dir: Path) -> dict:
    """Load, convert, and analyze one recording document from MongoDB."""
    filename = recording.get("audio_filename")
    if not filename:
        raise RuntimeError("Recording has no audio_filename")

    src_path = audio_dir / filename
    if not src_path.exists():
        raise FileNotFoundError(f"Audio file not found: {src_path}")

    # convert to WAV via ffmpeg
    wav_dir = audio_dir / "wav_cache"
    wav_path = convert_to_wav(src_path, wav_dir)

    # load WAV file with soundfile
    samples, sample_rate = sf.read(str(wav_path), dtype="float32")

    if samples.ndim == 1:
        waveform_np = samples[np.newaxis, :]
    else:
        waveform_np = samples.T

    waveform = torch.from_numpy(waveform_np)

    result = estimate_pitch(waveform, sample_rate)
    if result is None:
        raise RuntimeError("Could not estimate a stable pitch")

    pitch_hz, confidence = result
    note = hz_to_note(pitch_hz)

    return {
        "pitch_hz": pitch_hz,
        "pitch_note": note,
        "confidence": confidence,
        "method": "torchcrepe-tiny",
    }


def worker_loop() -> None:
    """Continuously look for pending recordings and analyze them."""
    db = get_db()
    audio_dir = get_audio_dir()

    print(f"[worker] Watching for recordings in: {audio_dir}")

    while True:
        pending = list(db.recordings.find({"status": "pending"}).limit(5))
        if not pending:
            print("[worker] No pending recordings.")
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        print(f"[worker] Found {len(pending)} pending recording(s).")

        for rec in pending:
            rec_id = rec["_id"]
            try:
                analysis = analyze_recording(rec, audio_dir)
                db.recordings.update_one(
                    {"_id": rec_id},
                    {
                        "$set": {
                            "analysis": analysis,
                            "status": "done",
                            "updated_at": datetime.utcnow(),
                            "error_message": None,
                        }
                    },
                )
                print(
                    f"[worker] Updated recording {rec_id} "
                    f"-> {analysis['pitch_note']} ({analysis['pitch_hz']:.1f} Hz)"
                )
            except Exception as exc:  # pylint: disable=broad-except
                db.recordings.update_one(
                    {"_id": rec_id},
                    {
                        "$set": {
                            "status": "error",
                            "error_message": str(exc),
                            "updated_at": datetime.utcnow(),
                        }
                    },
                )
                print(f"[worker] Could not estimate pitch for {rec_id}: {exc}")

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    worker_loop()
