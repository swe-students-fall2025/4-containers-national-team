"""Unit tests for main.py in the machine-learning client."""

# pylint: disable=missing-function-docstring,too-few-public-methods

from pathlib import Path
import sys

import numpy as np
import pytest

# Make sure the parent directory (containing main.py) is on the path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# NOTE:
# The ML worker in main.py depends on heavy audio/ML libraries
# (torch/torchcrepe/soundfile + native libs and model weights) that are not
# guaranteed to be available on the grading / CI machines. When those
# libraries cannot be imported they raise OSError. In that case we treat the
# ML worker as an optional component and skip this entire test module instead
# of failing the test run.


# Import the application module. On GitHub runners, importing soundfile/torch
# can fail if system libs are missing; in that case we skip this module.
try:
    import main  # pylint: disable=import-error, wrong-import-position
except OSError as exc:  # soundfile/torch shared libs missing on some systems
    pytest.skip(
        f"Skipping ML client tests because dependencies cannot load: {exc}",
        allow_module_level=True,
    )


def test_get_audio_dir_respects_env_and_creates_dir(tmp_path, monkeypatch):
    audio_root = tmp_path / "recordings"
    monkeypatch.setenv("AUDIO_DIR", str(audio_root))

    path = main.get_audio_dir()

    assert path == audio_root.resolve()
    assert path.exists()
    assert path.is_dir()


def test_hz_to_note_basic_and_guard():
    assert main.hz_to_note(440.0) == "A4"  # concert A
    assert main.hz_to_note(261.63) == "C4"  # middle C approx
    assert main.hz_to_note(0.0) == "N/A"
    assert main.hz_to_note(-10.0) == "N/A"


def test_convert_to_wav_invokes_ffmpeg(tmp_path, monkeypatch):
    input_path = tmp_path / "input.webm"
    input_path.write_bytes(b"fake webm")

    out_dir = tmp_path / "out"

    calls: dict[str, object] = {}

    def fake_run(cmd, check):  # pylint: disable=unused-argument
        calls["cmd"] = cmd
        calls["check"] = check
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
    torch_mod = main.torch

    waveform = torch_mod.zeros(1, 16000)
    sample_rate = 16000

    def fake_predict(*args, **kwargs):  # pylint: disable=unused-argument
        pitch = torch_mod.tensor([[220.0, 220.0]])
        periodicity = torch_mod.tensor([[0.9, 0.8]])
        return pitch, periodicity

    def fake_median(tensor, win):  # pylint: disable=unused-argument
        return tensor

    monkeypatch.setattr(main.torchcrepe, "predict", fake_predict)
    monkeypatch.setattr(main.torchcrepe.filter, "median", fake_median)

    pitch_hz, confidence = main.estimate_pitch(waveform, sample_rate)

    assert pitch_hz == pytest.approx(220.0)
    assert 0.0 <= confidence <= 1.0


def test_estimate_pitch_returns_none_when_no_valid(monkeypatch):
    torch_mod = main.torch

    waveform = torch_mod.zeros(1, 16000)
    sample_rate = 16000

    def fake_predict(*args, **kwargs):  # pylint: disable=unused-argument
        pitch = torch_mod.full((1, 3), 200.0)
        periodicity = torch_mod.zeros((1, 3))  # all below threshold
        return pitch, periodicity

    def fake_median(tensor, win):  # pylint: disable=unused-argument
        return tensor

    monkeypatch.setattr(main.torchcrepe, "predict", fake_predict)
    monkeypatch.setattr(main.torchcrepe.filter, "median", fake_median)

    result = main.estimate_pitch(waveform, sample_rate)

    assert result is None


def test_analyze_recording_happy_path(tmp_path, monkeypatch):
    recording = {"audio_filename": "clip.webm"}
    audio_dir = tmp_path
    src_file = audio_dir / recording["audio_filename"]
    src_file.write_bytes(b"fake data")

    def fake_convert_to_wav(input_path, output_dir):
        assert input_path == src_file
        output_dir.mkdir(parents=True, exist_ok=True)
        wav_path = output_dir / "clip.wav"
        wav_path.write_bytes(b"fake wav")
        return wav_path

    monkeypatch.setattr(main, "convert_to_wav", fake_convert_to_wav)

    class FakeSF:
        "Fake SF"

        @staticmethod
        def read(path, dtype="float32"):  # pylint: disable=unused-argument
            samples = np.ones(16000, dtype=np.float32)
            return samples, 16000

    monkeypatch.setattr(main, "sf", FakeSF)

    def fake_estimate_pitch(waveform, sample_rate):  # pylint: disable=unused-argument
        return 440.0, 0.75

    monkeypatch.setattr(main, "estimate_pitch", fake_estimate_pitch)

    result = main.analyze_recording(recording, audio_dir)

    assert result["pitch_hz"] == pytest.approx(440.0)
    assert result["pitch_note"] == "A4"
    assert result["confidence"] == pytest.approx(0.75)
    assert result["method"] == "torchcrepe-tiny"


def test_analyze_recording_missing_filename_raises(tmp_path):
    with pytest.raises(RuntimeError):
        main.analyze_recording({}, tmp_path)


def test_analyze_recording_missing_file_raises(tmp_path):
    rec = {"audio_filename": "nope.webm"}
    with pytest.raises(FileNotFoundError):
        main.analyze_recording(rec, tmp_path)


# ----- worker_loop tests -----


class FakeCursor(list):
    """Mimic a MongoDB cursor with .limit()."""

    def limit(self, n):
        return FakeCursor(self[:n])


class FakeRecordings:
    """Mimic a fake recording."""

    def __init__(self, docs):
        self.docs = docs
        self.updates = []

    def find(self, query):
        _ = query
        return FakeCursor(self.docs)

    def update_one(self, filter_, update):
        self.updates.append((filter_, update))


class FakeDB:
    """Mimic a fake database."""

    def __init__(self, docs):
        self.recordings = FakeRecordings(docs)


def test_worker_loop_processes_pending_recording(monkeypatch, tmp_path):
    docs = [
        {"_id": "abc123", "status": "pending", "audio_filename": "clip.webm"},
    ]
    fake_db = FakeDB(docs)

    monkeypatch.setattr(main, "get_db", lambda: fake_db)
    monkeypatch.setattr(main, "get_audio_dir", lambda: tmp_path)

    def fake_analyze(recording, audio_dir):  # pylint: disable=unused-argument
        return {
            "pitch_hz": 440.0,
            "pitch_note": "A4",
            "confidence": 0.9,
            "method": "test",
        }

    monkeypatch.setattr(main, "analyze_recording", fake_analyze)

    sleep_calls = []

    def fake_sleep(seconds):
        sleep_calls.append(seconds)
        # Stop the infinite loop after one iteration
        raise KeyboardInterrupt()

    monkeypatch.setattr(main.time, "sleep", fake_sleep)

    with pytest.raises(KeyboardInterrupt):
        main.worker_loop()

    # Ensure we attempted to update the recording as "done"
    assert fake_db.recordings.updates, "worker_loop should update the recording"
    _filter, update = fake_db.recordings.updates[0]
    assert _filter == {"_id": "abc123"}
    assert update["$set"]["status"] == "done"
    assert update["$set"]["analysis"]["pitch_note"] == "A4"
    assert sleep_calls, "worker_loop should call time.sleep()"


def test_worker_loop_handles_analysis_error(monkeypatch, tmp_path):
    docs = [
        {"_id": "xyz789", "status": "pending", "audio_filename": "clip.webm"},
    ]
    fake_db = FakeDB(docs)

    monkeypatch.setattr(main, "get_db", lambda: fake_db)
    monkeypatch.setattr(main, "get_audio_dir", lambda: tmp_path)

    def fake_analyze(recording, audio_dir):  # pylint: disable=unused-argument
        raise RuntimeError("boom")

    monkeypatch.setattr(main, "analyze_recording", fake_analyze)

    def fake_sleep(seconds):  # pylint: disable=unused-argument
        raise KeyboardInterrupt()

    monkeypatch.setattr(main.time, "sleep", fake_sleep)

    with pytest.raises(KeyboardInterrupt):
        main.worker_loop()

    assert (
        fake_db.recordings.updates
    ), "worker_loop should update the recording on error"
    _filter, update = fake_db.recordings.updates[0]
    assert _filter == {"_id": "xyz789"}
    assert update["$set"]["status"] == "error"
    assert "boom" in update["$set"]["error_message"]
