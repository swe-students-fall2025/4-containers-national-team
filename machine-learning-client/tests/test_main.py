"""Unit tests for main.py (ML worker)."""

from pathlib import Path
import sys

import numpy as np
import pytest
import torch

# Make sure the parent directory (containing main.py) is on the path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main  # pylint: disable=import-error, wrong-import-position


def test_get_audio_dir_respects_env_and_creates_dir(tmp_path, monkeypatch):
    """get_audio_dir should use AUDIO_DIR env var and create the directory."""
    audio_root = tmp_path / "recordings"
    monkeypatch.setenv("AUDIO_DIR", str(audio_root))

    path = main.get_audio_dir()

    assert path == audio_root.resolve()
    assert path.exists()
    assert path.is_dir()


def test_hz_to_note_basic():
    """Check a normal note and the <= 0 guard."""
    assert main.hz_to_note(440.0) == "A4"  # concert A
    assert main.hz_to_note(0.0) == "N/A"
    assert main.hz_to_note(-10.0) == "N/A"


def test_convert_to_wav_invokes_ffmpeg(tmp_path, monkeypatch):
    """convert_to_wav should call ffmpeg and produce a .wav path."""
    input_path = tmp_path / "input.webm"
    input_path.write_bytes(b"fake webm")

    out_dir = tmp_path / "out"

    calls: dict[str, object] = {}

    def fake_run(cmd, check):  # pylint: disable=unused-argument
        """Fake subprocess.run that records the command and creates an output file."""
        calls["cmd"] = cmd
        calls["check"] = check
        # Simulate ffmpeg writing the output file
        out = Path(cmd[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"fake wav")

    monkeypatch.setattr(main.subprocess, "run", fake_run)

    wav_path = main.convert_to_wav(input_path, out_dir)

    assert wav_path.parent == out_dir
    assert wav_path.suffix == ".wav"
    assert wav_path.exists()

    assert calls["cmd"][0] == "ffmpeg"
    assert calls["check"] is True


def test_estimate_pitch_uses_torchcrepe(monkeypatch):
    """estimate_pitch should average valid pitch values and return a confidence."""
    waveform = torch.zeros(1, 16000)
    sample_rate = 16000

    def fake_predict(  # pylint: disable=too-many-arguments,unused-argument
        waveform_arg, sample_rate_arg
    ):
        """Fake torchcrepe.predict that returns two frames of 220 Hz."""
        assert waveform_arg is waveform
        assert sample_rate_arg == sample_rate
        # Two frames of 220 Hz with high periodicity
        pitch = torch.tensor([[220.0, 220.0]])
        periodicity = torch.tensor([[0.9, 0.8]])
        return pitch, periodicity

    def fake_median(tensor, win):  # pylint: disable=unused-argument
        """Fake median filter that just returns the input tensor."""
        return tensor

    # Patch torchcrepe functions used by estimate_pitch
    monkeypatch.setattr(main.torchcrepe, "predict", fake_predict)
    monkeypatch.setattr(main.torchcrepe.filter, "median", fake_median)

    pitch_hz, confidence = main.estimate_pitch(waveform, sample_rate)

    assert pitch_hz == pytest.approx(220.0)
    assert 0.0 <= confidence <= 1.0


def test_analyze_recording_happy_path(tmp_path, monkeypatch):
    """analyze_recording should return a dict with pitch info for a valid file."""
    # Arrange: fake recording doc & audio dir
    recording = {"audio_filename": "clip.webm"}
    audio_dir = tmp_path
    src_file = audio_dir / recording["audio_filename"]
    src_file.write_bytes(b"fake data")

    def fake_convert_to_wav(input_path, output_dir):
        """Fake convert_to_wav that creates a dummy WAV file."""
        assert input_path == src_file
        output_dir.mkdir(parents=True, exist_ok=True)
        wav_path = output_dir / "clip.wav"
        wav_path.write_bytes(b"fake wav")
        return wav_path

    monkeypatch.setattr(main, "convert_to_wav", fake_convert_to_wav)

    class FakeSF:  # pylint: disable=too-few-public-methods
        """Fake stand-in for the soundfile module."""

        @staticmethod
        def read(path, dtype="float32"):  # pylint: disable=unused-argument
            """Return 1 second of dummy audio."""
            samples = np.ones(16000, dtype=np.float32)
            return samples, 16000

    monkeypatch.setattr(main, "sf", FakeSF)

    def fake_estimate_pitch(_waveform, _sample_rate):  # pylint: disable=unused-argument
        """Fake estimate_pitch that returns a fixed pitch and confidence."""
        return 440.0, 0.75

    monkeypatch.setattr(main, "estimate_pitch", fake_estimate_pitch)

    result = main.analyze_recording(recording, audio_dir)

    assert result["pitch_hz"] == pytest.approx(440.0)
    assert result["pitch_note"] == "A4"
    assert result["confidence"] == pytest.approx(0.75)
    assert result["method"] == "torchcrepe-tiny"


def test_analyze_recording_missing_filename_raises(tmp_path):
    """If audio_filename is missing, analyze_recording should raise."""
    with pytest.raises(RuntimeError):
        main.analyze_recording({}, tmp_path)


def test_analyze_recording_missing_file_raises(tmp_path):
    """If the referenced file does not exist, we should get FileNotFoundError."""
    rec = {"audio_filename": "nope.webm"}
    with pytest.raises(FileNotFoundError):
        main.analyze_recording(rec, tmp_path)
