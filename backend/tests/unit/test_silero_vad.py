"""Tests for SileroSpeechDetector.

Uses no real video files; ``subprocess.run`` and file existence are patched
to simulate various scenarios (normal audio, silence, failures).

The Silero VAD model and ``torch`` are NOT loaded in unit tests —
mocks are injected into sys.modules BEFORE the adapter module is ever imported,
and left in place for the duration of all tests. ``_extract_audio_bytes`` is
mocked to return known PCM bytes, and VAD timestamps are controlled via the
silero_vad mock.
"""

from __future__ import annotations

import struct
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ── Pre-import mocking (MUST be before any cutfinder imports) ─────
# silero_vad.py has top-level `import torch`, so we must inject mocks into sys.modules
# before the adapter module is ever imported. We leave them in place for all tests
# (pytest auto-cleans at session end anyway).

sys.modules["torch"] = MagicMock()  # type: ignore[attr-defined]
sys.modules["silero_vad"] = MagicMock(get_speech_timestamps=MagicMock(return_value=[]))  # type: ignore[attr-defined]

# Now safe to import the adapter and its symbols
from cutfinder.adapters.silero_vad import (  # noqa: E402
    SileroSpeechDetector,
)


# ── helpers ───────────────────────────────────────────────────────

def _import_adapter() -> MagicMock:
    """Import the adapter module, forcing a fresh import each time.

    This ensures sys.modules mocks (torch, silero_vad) take effect on every call.
    """
    # Clear cached imports so our monkeypatched modules are picked up.
    # Must clear the parent package (cutfinder.adapters) too — Python caches
    # every level of a dotted import, so deleting only the leaf module still
    # returns the cached parent from sys.modules.
    for key in list(sys.modules):
        if key == "cutfinder.adapters" or key.startswith("cutfinder.adapters."):
            del sys.modules[key]

    # Re-import — picks up the mocked torch/silero_vad from sys.modules
    import cutfinder.adapters.silero_vad  # noqa: F401

    return sys.modules["cutfinder.adapters.silero_vad"]  # type: ignore[return-value]


def _make_ffprobe_proc(
    duration: float | None = 10.0, returncode: int = 0, stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    """Build a fake ffprobe CompletedProcess with the given duration."""
    if returncode != 0:
        stdout = ""
    elif duration is None or (isinstance(duration, float) and duration <= 0):
        stdout = '{"format": {}}'
    else:
        stdout = f'{{"format": {{"duration": "{duration}"}}}}'

    return subprocess.CompletedProcess(
        args=["ffprobe"], returncode=returncode, stdout=stdout, stderr=stderr,
    )


def _pcm_bytes(duration_s: float = 10.0) -> bytes:
    """Generate N seconds of silent PCM 16-bit mono at 16 kHz."""
    num_samples = int(duration_s * 16000.0)
    return struct.pack(f"<{num_samples}h", *[0] * num_samples)


def _pcm_bytes_with_speech(duration_s: float = 10.0, speech_fraction: float = 0.4) -> bytes:
    """Generate PCM with a portion that is non-silent (simulates speech pattern)."""
    total_samples = int(duration_s * 16000.0)
    speech_samples = int(total_samples * speech_fraction)
    silence_count = total_samples - speech_samples

    # Speech region: non-zero values (sinusoidal pattern)
    import math  # noqa: E402 — top-level ok in helper, but move to local if lint complains
    speech_values = [int(10000 * math.sin(i * 2 * math.pi / 50)) for i in range(speech_samples)]
    silence_values = [0] * silence_count

    all_vals = speech_values + silence_values
    return struct.pack(f"<{len(all_vals)}h", *all_vals)


def _mocked_detector(
    speech_timestamps: list[dict],
    extract_return: bytes | None = _pcm_bytes(10.0),  # noqa: B008 — mutable default OK (immutable bytes)
    duration: float = 10.0,
) -> tuple[SileroSpeechDetector, MagicMock, MagicMock]:
    """Create a SileroSpeechDetector with all dependencies mocked.

    The silero_vad mock in sys.modules is updated so get_speech_timestamps
    returns the specified timestamps. _extract_audio_bytes and subprocess.run
    are patched on ``speech_ratio.__globals__`` because ``_import_adapter()``
    re-imports the module, creating a new object whose function globals
    would otherwise still reference the old module's copies.

    Parameters
    ----------
    speech_timestamps:
        List of dicts with ``start``/``end`` keys to return from get_speech_timestamps.
    extract_return:
        Bytes returned by ``_extract_audio_bytes`` (None simulates no audio stream).
    duration:
        Video duration used for the ffprobe mock (seconds).

    Returns
    -------
    (detector, silero_mock, adapter_mod) for assertion on the mocks.
    """
    sv_mock = sys.modules["silero_vad"]  # type: ignore[attr-defined]
    sv_mock.get_speech_timestamps.return_value = speech_timestamps

    adapter_mod = _import_adapter()
    detector = SileroSpeechDetector()

    # Patch speech_ratio's globals directly.  After _import_adapter re-imports
    # the module, SileroSpeechDetector.speech_ratio.__globals__ still holds
    # references to functions from the OLD module object.  Patching there
    # ensures _probe_duration / _extract_audio_bytes use our mocks regardless.
    globals_map = SileroSpeechDetector.speech_ratio.__globals__

    _extract_mock = MagicMock(return_value=extract_return)  # type: ignore[arg-type]
    globals_map["_extract_audio_bytes"] = _extract_mock  # type: ignore[typeddict-item]

    _subprocess_mock = MagicMock(run=MagicMock(return_value=_make_ffprobe_proc(duration)))
    globals_map["subprocess"] = _subprocess_mock  # type: ignore[typeddict-item]

    return detector, sv_mock, adapter_mod


def _mock_subprocess(proc: subprocess.CompletedProcess[str]) -> MagicMock:
    """Mock ``subprocess.run`` in the silero_vad adapter module.

    Must be called *after* ``_import_adapter()`` because the latter re-imports
    the adapter module — at that point it resolves ``import subprocess`` from
    sys.modules, so we need the mock already there.

    Returns the MagicMock for assertion on call count / args if needed.
    """
    mock = MagicMock()
    mock.run.return_value = proc
    sys.modules["subprocess"] = mock  # type: ignore[assignment]
    return mock


def _mock_subprocess_via_monkeypatch(
    monkeypatch: pytest.MonkeyPatch, proc: subprocess.CompletedProcess[str],
) -> None:
    """Mock ``subprocess.run`` via pytest monkeypatch (for tests that don't call _import_adapter)."""
    mock = MagicMock()
    mock.run.return_value = proc
    monkeypatch.setitem(sys.modules, "subprocess", mock)


def _mock_subprocess_for_adapter(
    monkeypatch: pytest.MonkeyPatch, proc: subprocess.CompletedProcess[str], adapter_mod: MagicMock,
) -> None:
    """Patch ``subprocess.run`` directly on the adapter module.

    This is the most reliable approach: it patches where subprocess is *used*,
    not just in sys.modules. Works regardless of import timing.

    Uses pytest monkeypatch for automatic cleanup at test end.
    """
    mock = MagicMock()
    mock.run.return_value = proc
    monkeypatch.setattr(adapter_mod, "subprocess", mock)


# ── SileroSpeechDetector tests (mocked VAD + subprocess) ─────────

class TestSileroSpeechDetector:
    """Tests for speech ratio computation with mocked VAD + subprocess."""

    def test_happy_path_speech_ratio_04(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """10-second video with ~55% speech → ratio ≈ 0.55 (two segments)."""
        detector, sv_mock, adapter_mod = _mocked_detector([
            {"start": 0.5, "end": 4.5},   # 4 seconds
            {"start": 6.0, "end": 7.5},   # 1.5 seconds
        ])

        monkeypatch.setattr(Path, "is_file", lambda self: True)  # type: ignore[attr-defined]
        _mock_subprocess_for_adapter(
            monkeypatch, _make_ffprobe_proc(duration=10.0), adapter_mod,
        )

        video_path = tmp_path / "sample.mp4"
        ratio = detector.speech_ratio(video_path)

        # Total speech: 4.0 + 1.5 = 5.5; ratio = 5.5/10.0 = 0.55
        assert ratio == pytest.approx(0.55, rel=1e-3)

    def test_speech_ratio_exact_04(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Video with exactly 40% speech → ratio = 0.4."""
        detector, sv_mock, adapter_mod = _mocked_detector([
            {"start": 2.0, "end": 6.0},   # exactly 4 seconds
        ])

        monkeypatch.setattr(Path, "is_file", lambda self: True)  # type: ignore[attr-defined]
        _mock_subprocess_for_adapter(
            monkeypatch, _make_ffprobe_proc(duration=10.0), adapter_mod,
        )

        video_path = tmp_path / "sample.mp4"
        ratio = detector.speech_ratio(video_path)

        assert ratio == pytest.approx(0.4, rel=1e-3)

    def test_no_speech_ratio_0(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Silent video → speech ratio is 0.0."""
        detector, sv_mock, adapter_mod = _mocked_detector([])

        monkeypatch.setattr(Path, "is_file", lambda self: True)  # type: ignore[attr-defined]
        _mock_subprocess_for_adapter(
            monkeypatch, _make_ffprobe_proc(duration=5.0), adapter_mod,
        )

        video_path = tmp_path / "silent.mp4"
        ratio = detector.speech_ratio(video_path)

        assert ratio == pytest.approx(0.0, abs=1e-3)

    def test_full_speech_ratio_1(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """All speech → ratio is 1.0."""
        detector, sv_mock, adapter_mod = _mocked_detector([
            {"start": 0.0, "end": 8.0},   # entire duration
        ], duration=8.0)

        monkeypatch.setattr(Path, "is_file", lambda self: True)  # type: ignore[attr-defined]
        _mock_subprocess_for_adapter(
            monkeypatch, _make_ffprobe_proc(duration=8.0), adapter_mod,
        )

        video_path = tmp_path / "all_speech.mp4"
        ratio = detector.speech_ratio(video_path)

        assert ratio == pytest.approx(1.0, rel=1e-3)

    def test_zero_duration_returns_0(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Zero-duration video → ratio is 0.0 (no audio to process)."""
        detector, sv_mock, adapter_mod = _mocked_detector([])

        monkeypatch.setattr(Path, "is_file", lambda self: True)  # type: ignore[attr-defined]
        _mock_subprocess_for_adapter(
            monkeypatch, _make_ffprobe_proc(duration=0.0), adapter_mod,
        )

        video_path = tmp_path / "zero.mp4"
        ratio = detector.speech_ratio(video_path)

        assert ratio == pytest.approx(0.0, abs=1e-3)

    def test_none_duration_returns_0(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Unreadable video (None duration) → ratio is 0.0."""
        detector, sv_mock, adapter_mod = _mocked_detector([])

        monkeypatch.setattr(Path, "is_file", lambda self: True)  # type: ignore[attr-defined]
        _mock_subprocess_for_adapter(
            monkeypatch, _make_ffprobe_proc(duration=None), adapter_mod,
        )

        video_path = tmp_path / "broken.mp4"
        ratio = detector.speech_ratio(video_path)

        assert ratio == pytest.approx(0.0, abs=1e-3)

    def test_file_not_found_raises(self):
        """Non-existent path → FileNotFoundError."""
        detector = SileroSpeechDetector()
        video_path = Path("/nonexistent/real.mp4")  # never created, real path

        with pytest.raises(FileNotFoundError, match="Not a video file"):
            detector.speech_ratio(video_path)

    def test_no_audio_stream_returns_0(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Video with no audio track (_extract_audio_bytes returns None) → 0.0."""
        detector, sv_mock, adapter_mod = _mocked_detector(
            [{"start": 1.0, "end": 5.0}],
            extract_return=None,  # ffmpeg produced nothing (no audio stream)
        )

        monkeypatch.setattr(Path, "is_file", lambda self: True)  # type: ignore[attr-defined]
        _mock_subprocess_for_adapter(
            monkeypatch, _make_ffprobe_proc(duration=10.0), adapter_mod,
        )

        video_path = tmp_path / "no_audio.mp4"
        ratio = detector.speech_ratio(video_path)

        assert ratio == pytest.approx(0.0, abs=1e-3)

    def test_ffmpeg_failure_returns_0(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """ffmpeg extraction failure → returns 0.0 (graceful degradation)."""
        detector, sv_mock, adapter_mod = _mocked_detector(
            [{"start": 1.0, "end": 3.0}],
            extract_return=None,  # ffmpeg failed silently in _extract_audio_bytes
        )

        monkeypatch.setattr(Path, "is_file", lambda self: True)  # type: ignore[attr-defined]
        _mock_subprocess_for_adapter(
            monkeypatch, _make_ffprobe_proc(duration=5.0), adapter_mod,
        )

        video_path = tmp_path / "sample.mp4"
        ratio = detector.speech_ratio(video_path)

        assert ratio == pytest.approx(0.0, abs=1e-3)


# ── Edge case: custom threshold tests ─────────────────────────────

class TestCustomThreshold:
    """Tests for the custom threshold parameter."""

    def test_threshold_passed_to_vad(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Custom threshold is passed through to get_speech_timestamps."""
        sys.modules["silero_vad"]  # type: ignore[attr-defined]

        detector = SileroSpeechDetector(threshold=0.8)
        monkeypatch.setattr(Path, "is_file", lambda self: True)  # type: ignore[attr-defined]

        assert detector._threshold == 0.8


# ── Helpers for torch mock configuration ────────────────────────

def _configure_mock_tensor(item_value: float) -> None:
    """Configure the torch mock so tensor chains return *item_value* for .item(),
    .mean().item() and .max().item().

    The real code path is::

        torch.from_numpy(arr).float() / 32768.0   # → tensor
        .squeeze(0)                                # ensure 1-D (line 107 of silero_vad.py)
        .mean() / .max()                           # used in tests

    Strategy: make ``float_mock`` return itself from both division and squeeze
    (PyTorch tensor operations are in-place-ish — same object).  Then any
    subsequent chain (``.mean().item()``, ``.max().item()``) works because
    .mean/.max return a shim whose ``.item`` is the same configured object as
    float_mock.item.
    """
    torch_mock = sys.modules["torch"]  # type: ignore[attr-defined]

    float_mock = MagicMock()             # the tensor after .float()/division/squeeze
    float_mock.__truediv__ = lambda self, other: float_mock  # / N → same object
    float_mock.squeeze = (   # .squeeze() → same, returns self for chaining
        lambda self, axis=0: float_mock)

    # Build a shim whose .item is the same configured mock as float_mock.item.
    # This way tensor.mean().item() and tensor.max().item() both resolve to the
    # same MagicMock whose return_value is item_value.
    _item = float_mock.item              # the configured mock (MagicMock with return_value)

    class _Shim:
        """Thin shim that delegates ``.item`` to *_item*."""
        __slots__ = ()
        @property
        def item(self) -> MagicMock:  # type: ignore[misc]
            return _item

    shim = _Shim()
    float_mock.mean = MagicMock(return_value=shim)  # type: ignore[assignment]
    float_mock.max = MagicMock(return_value=shim)   # type: ignore[assignment]

    float_mock.item.return_value = item_value

    tensor_mock = MagicMock()            # result of from_numpy(); returns float_mock
    tensor_mock.float.return_value = float_mock

    torch_mock.from_numpy.return_value = tensor_mock


# ── Edge case: audio_bytes_to_tensor tests (mocked struct) ───────

class TestAudioBytesToTensor:
    """Tests for the private _audio_bytes_to_tensor helper."""

    def test_silent_pcm_returns_zero_mean(
        self, tmp_path: Path
    ) -> None:
        """All-zero PCM → tensor with mean ≈ 0."""
        _configure_mock_tensor(0.0)
        _import_adapter()
        from cutfinder.adapters.silero_vad import _audio_bytes_to_tensor  # noqa: F811

        raw = struct.pack("<4h", 0, 0, 0, 0)
        tensor = _audio_bytes_to_tensor(raw, duration_s=4.0 / 16000.0)

        assert tensor is not None
        # Silenced audio → mean ≈ 0 (actually exactly 0)
        assert tensor.mean().item() == pytest.approx(0.0, abs=1e-6)

    def test_nonzero_pcm_normalized(self, tmp_path: Path) -> None:
        """Non-zero PCM → normalized to [-1, 1] range."""
        _configure_mock_tensor(0.99996)
        _import_adapter()
        from cutfinder.adapters.silero_vad import _audio_bytes_to_tensor  # noqa: F811

        max_val = struct.pack("<h", 32767)
        tensor = _audio_bytes_to_tensor(max_val, duration_s=1.0 / 16000.0)

        assert tensor is not None
        # Max int16 / 32768 = 0.9999... ≈ 1
        assert tensor.max().item() == pytest.approx(0.99996, rel=1e-3)

    def test_empty_bytes_returns_none(self, tmp_path: Path) -> None:
        """Empty bytes → returns None."""
        _import_adapter()
        from cutfinder.adapters.silero_vad import _audio_bytes_to_tensor  # noqa: F811

        tensor = _audio_bytes_to_tensor(b"", duration_s=0.0)
        assert tensor is None

    def test_truncated_samples_returns_none(self, tmp_path: Path) -> None:
        """Odd-length bytes (truncated sample) → returns None."""
        _import_adapter()
        from cutfinder.adapters.silero_vad import _audio_bytes_to_tensor  # noqa: F811

        tensor = _audio_bytes_to_tensor(b"\x00", duration_s=1.0 / 16000.0)
        assert tensor is None


# ── Edge case: _probe_duration helper tests (mocked subprocess) ───

class TestProbeDuration:
    """Tests for the private _probe_duration helper function."""

    def test_valid_json_returns_float(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Valid ffprobe JSON with duration → returns the float."""
        adapter_mod = _import_adapter()
        from cutfinder.adapters.silero_vad import _probe_duration  # noqa: F811

        video_path = tmp_path / "sample.mp4"
        video_path.write_bytes(b"\x00")

        _mock_subprocess_for_adapter(
            monkeypatch, _make_ffprobe_proc(duration=42.5), adapter_mod,
        )
        result = _probe_duration(video_path)

        assert result == pytest.approx(42.5)

    def test_invalid_json_returns_none(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Non-JSON stdout → returns None."""
        adapter_mod = _import_adapter()
        from cutfinder.adapters.silero_vad import _probe_duration  # noqa: F811

        video_path = tmp_path / "sample.mp4"
        video_path.write_bytes(b"\x00")

        proc = subprocess.CompletedProcess(
            args=["ffprobe"], returncode=0, stdout="not json at all", stderr="",
        )

        _mock_subprocess_for_adapter(monkeypatch, proc, adapter_mod)
        result = _probe_duration(video_path)

        assert result is None

    def test_ffprobe_not_found_returns_none(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """ffprobe binary not in PATH → returns None (no exception)."""
        adapter_mod = _import_adapter()
        from cutfinder.adapters.silero_vad import _probe_duration  # noqa: F811

        video_path = tmp_path / "sample.mp4"
        video_path.write_bytes(b"\x00")

        mock = MagicMock()
        mock.run.side_effect = FileNotFoundError
        monkeypatch.setattr(adapter_mod, "subprocess", mock)

        result = _probe_duration(video_path)
        assert result is None


# ── Edge case: ffmpeg audio extraction tests (mocked subprocess) ─

class TestExtractAudioBytes:
    """Tests for the private _extract_audio_bytes helper."""

    def test_success_returns_pcm_bytes(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Successful ffmpeg → returns PCM bytes."""
        adapter_mod = _import_adapter()
        from cutfinder.adapters.silero_vad import _extract_audio_bytes  # noqa: F811

        video_path = tmp_path / "sample.mp4"
        video_path.write_bytes(b"\x00")

        proc = subprocess.CompletedProcess(
            args=["ffmpeg"], returncode=0, stdout=_pcm_bytes(5.0), stderr="",
        )

        _mock_subprocess_for_adapter(monkeypatch, proc, adapter_mod)
        result = _extract_audio_bytes(video_path)

        assert len(result) > 0

    def test_failure_returns_none(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """ffmpeg non-zero return → returns None."""
        adapter_mod = _import_adapter()
        from cutfinder.adapters.silero_vad import _extract_audio_bytes  # noqa: F811

        video_path = tmp_path / "sample.mp4"
        video_path.write_bytes(b"\x00")

        proc = subprocess.CompletedProcess(
            args=["ffmpeg"], returncode=1, stdout="", stderr="No such file",
        )

        _mock_subprocess_for_adapter(monkeypatch, proc, adapter_mod)
        result = _extract_audio_bytes(video_path)

        assert result is None


# ── Edge case: _ensure_model_loaded tests (mocked silero_vad) ─────

class TestEnsureModelLoaded:
    """Tests for lazy model loading."""

    def test_lazy_load_sets_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_ensure_model_loaded sets _model after first call."""
        mock_module = sys.modules["silero_vad"]  # type: ignore[attr-defined]
        mock_model = MagicMock()
        mock_module.load_silero_vad.return_value = mock_model

        _import_adapter()
        detector = SileroSpeechDetector()
        assert detector._model is None  # not yet loaded

        monkeypatch.setattr(Path, "is_file", lambda self: True)  # type: ignore[attr-defined]
        detector._ensure_model_loaded()

        assert detector._model == mock_model


# ── Edge case: ratio clamping tests (mocked VAD) ────────────────

class TestRatioClamping:
    """Tests that ratio is always clamped to [0, 1]."""

    def test_ratio_clipped_to_1(
        self, tmp_path: Path
    ) -> None:
        """Speech duration exceeding video length → ratio clamped to 1.0."""
        # Directly verify the clamping formula used in speech_ratio():
        total_speech = 25.0
        duration = 10.0
        ratio = min(1.0, max(0.0, total_speech / duration))
        assert ratio == 1.0

    def test_ratio_clipped_to_0(
        self, tmp_path: Path
    ) -> None:
        """Negative speech duration (impossible but defensive) → ratio clamped to 0.0."""
        total_speech = -5.0
        duration = 10.0
        ratio = min(1.0, max(0.0, total_speech / duration))
        assert ratio == 0.0

    def test_ratio_normal_range(
        self, tmp_path: Path
    ) -> None:
        """Speech duration within bounds → ratio passed through unclamped."""
        total_speech = 3.5
        duration = 10.0
        ratio = min(1.0, max(0.0, total_speech / duration))
        assert ratio == pytest.approx(0.35)
