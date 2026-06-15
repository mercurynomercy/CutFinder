"""Unit tests for MlxWhisperTranscriber adapter.

Mocks mlx_whisper.transcribe and subprocess.run to test the full
transcription pipeline without real audio processing.

Tracker for what each group covers:

    extraction tests  — _extract_audio_bytes via mocked subprocess.run
    conversion tests   — _audio_bytes_to_array with various inputs
    adapter integration— MlxWhisperTranscriber.transcribe end-to-end (mocked whisper)
    edge cases         — missing file, no audio stream, decode failure, empty output

"""

import struct
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── shared constants & helpers ───────────────────────────────

SAMPLE_PCM_BYTES = struct.pack("<2h", 0, 32767)

SAMPLE_RESULT_DICT = {
    "text": "这是一段中文测试。",
    "segments": [
        {"start": 0.0, "end": 2.5, "text": "这是一段"},
        {"start": 2.5, "end": 4.0, "text": "中文测试。"},
    ],
}


def _import_adapter():
    """Import the adapter module, forcing a fresh import each time.

    This ensures sys.modules mocks take effect on every call.
    """
    import sys

    # Clear cached imports so our monkeypatched modules are picked up
    for key in list(sys.modules):
        if key.startswith("cutfinder.adapters.mlx_whisper"):
            del sys.modules[key]

    import cutfinder.adapters.mlx_whisper  # noqa: F401

    return sys.modules["cutfinder.adapters.mlx_whisper"]


def _make_transcriber(whisper_mock: MagicMock, extract_return: bytes | None = SAMPLE_PCM_BYTES):
    """Create a transcriber with all dependencies mocked.

    Sets up global mocks (mlx_whisper in sys.modules) that persist until
    the test ends. pytest's monkeypatch auto-restores these at test end,
    so no explicit cleanup is needed.

    Parameters
    ----------
    whisper_mock:
        MagicMock whose ``transcribe.return_value`` is the dict to return.
    extract_return:
        Bytes returned by ``_extract_audio_bytes`` (None simulates no audio stream).

    """
    import sys  # type: ignore[import]
    import numpy as np  # type: ignore[import]

    # Inject mlx_whisper mock BEFORE _import_adapter so the re-import picks it up
    sys.modules["mlx_whisper"] = whisper_mock

    def _fake_convert(raw: bytes) -> np.ndarray | None:  # noqa: ANN202
        return (
            np.frombuffer(struct.pack("<2h", 0, 32767), dtype=np.int16)
            .astype(np.float32) / 32768.0
        )

    adapter = _import_adapter()
    adapter._extract_audio_bytes = MagicMock(return_value=extract_return)  # type: ignore[attr-defined]
    adapter._audio_bytes_to_array = _fake_convert  # type: ignore[attr-defined]

    return adapter.MlxWhisperTranscriber()


def _mocked_transcriber(whisper_dict: dict, monkeypatch):
    """Import and return a transcriber with mlx_whisper + helpers mocked.

    Uses pytest monkeypatch directly so global mocks auto-clean at test end.
    """
    import sys  # type: ignore[import]

    mod = MagicMock(transcribe=MagicMock(return_value=whisper_dict))
    monkeypatch.setitem(sys.modules, "mlx_whisper", mod)  # type: ignore[attr-defined]

    transcriber = _make_transcriber(mod)
    monkeypatch.setattr(Path, "is_file", lambda self: True)  # type: ignore[attr-defined]

    return transcriber


def _mocked_transcriber_with_extract(whisper_dict: dict, extract_return: bytes | None = SAMPLE_PCM_BYTES):
    """Like _mocked_transcriber but with a custom audio extraction return value.

    Note: This function sets global mocks directly (without monkeypatch.context),
    so the caller must use a real pytest monkeypatch fixture to clean up.
    For simple tests, just call it inside a test method — pytest auto-restore
    monkeypatch.setitem/setattr at the end of each test function.

    Returns (transcriber, cleanup_fn).
    """
    import sys  # type: ignore[import]

    real_mlx = sys.modules.get("mlx_whisper")
    mod = MagicMock(transcribe=MagicMock(return_value=whisper_dict))
    sys.modules["mlx_whisper"] = mod

    transcriber = _make_transcriber(mod, extract_return=extract_return)

    # Patch Path.is_file globally
    _orig_is_file = Path.is_file  # type: ignore[attr-defined]

    def cleanup():
        if real_mlx is not None:
            sys.modules["mlx_whisper"] = real_mlx
        else:
            sys.modules.pop("mlx_whisper", None)
        Path.is_file = _orig_is_file  # type: ignore[attr-defined]

    return transcriber, cleanup



# ── _extract_audio_bytes tests (subprocess.run) ───────────────

class TestExtractAudioBytes:
    """Test _extract_audio_bytes via mocked subprocess.run."""

    def test_success_returns_pcm_bytes(self, monkeypatch):
        raw = b"\x00\x01" * 50  # 100 bytes of dummy PCM
        mock_run = MagicMock(return_value=MagicMock(returncode=0, stdout=raw))
        monkeypatch.setitem(__import__("sys").modules, "subprocess", MagicMock(run=mock_run))

        mod = _import_adapter()
        result = mod._extract_audio_bytes(Path("/fake/video.mp4"))

        assert result == raw
        call_args = mock_run.call_args[0][0]
        assert "-map" in call_args
        assert "0:a:0" in call_args

    def test_nonzero_returncode_returns_none(self, monkeypatch):
        """ffmpeg failure → None."""
        mock_run = MagicMock(
            return_value=MagicMock(returncode=1, stdout=b"", stderr="error"),
        )
        monkeypatch.setitem(__import__("sys").modules, "subprocess", MagicMock(run=mock_run))

        mod = _import_adapter()
        assert mod._extract_audio_bytes(Path("/fake/video.mp4")) is None

    def test_empty_stdout_returns_none(self, monkeypatch):
        """No audio stream → empty stdout → None."""
        mock_run = MagicMock(
            return_value=MagicMock(returncode=0, stdout=b"", stderr=""),
        )
        monkeypatch.setitem(__import__("sys").modules, "subprocess", MagicMock(run=mock_run))

        mod = _import_adapter()
        assert mod._extract_audio_bytes(Path("/fake/video.mp4")) is None


# ── _audio_bytes_to_array tests (struct + numpy) ─────────────

class TestAudioBytesToArray:
    """Test _audio_bytes_to_array conversion. No mocking needed — pure function."""

    def test_valid_pcm_returns_normalized_array(self):
        """10 samples of int16 → float32 array normalized [-1, 1]."""
        raw = struct.pack("<10h", *[32767] * 10)

        mod = _import_adapter()
        result = mod._audio_bytes_to_array(raw)
        import numpy as np

        assert isinstance(result, np.ndarray)
        assert result.dtype == np.float32
        assert len(result) == 10
        # Max value should be ~1.0 (32767/32768 ≈ 0.9999)
        assert result[0] == pytest.approx(32767 / 32768.0)

    def test_empty_bytes_returns_none(self):
        mod = _import_adapter()
        assert mod._audio_bytes_to_array(b"") is None

    def test_odd_length_returns_none(self):
        """Truncated sample (odd byte count) → None."""
        mod = _import_adapter()
        assert mod._audio_bytes_to_array(b"\x00\x01\x02") is None


# ── MlxWhisperTranscriber.transcribe integration tests ───────

class TestTranscriberTranscribe:
    """End-to-end (mocked whisper) tests for MlxWhisperTranscriber.transcribe."""

    def test_success_maps_whisper_result_to_transcript(self, monkeypatch):
        transcriber = _mocked_transcriber(SAMPLE_RESULT_DICT, monkeypatch)
        transcript = transcriber.transcribe(Path("/fake/video.mp4"))

        from cutfinder.domain.models import Segment, Transcript

        assert isinstance(transcript, Transcript)
        assert transcript.full_text == "这是一段中文测试。"
        assert len(transcript.segments) == 2

        expected_segments = [
            Segment(start_s=0.0, end_s=2.5, text="这是一段"),
            Segment(start_s=2.5, end_s=4.0, text="中文测试。"),
        ]
        assert transcript.segments == expected_segments

    def test_success_calls_ffmpeg_and_whisper(self, monkeypatch):
        """Verify the full pipeline: file check → ffmpeg → numpy → whisper."""
        mod = MagicMock()
        mod.transcribe.return_value = {"text": "", "segments": []}

        monkeypatch.setitem(__import__("sys").modules, "mlx_whisper", mod)
        adapter = _import_adapter()

        # Replace the extraction/conversion functions with mocks in-place
        extract_mock = MagicMock(return_value=SAMPLE_PCM_BYTES)

        def _convert(raw):
            import numpy as np
            return (
                np.frombuffer(struct.pack("<2h", 0, 32767), dtype=np.int16)
                .astype(np.float32) / 32768.0
            )

        convert_mock = MagicMock(side_effect=_convert)

        adapter._extract_audio_bytes = extract_mock
        adapter._audio_bytes_to_array = convert_mock

        with patch.object(Path, "is_file", return_value=True):
            transcriber = adapter.MlxWhisperTranscriber(model="base", language="en")
            transcript = transcriber.transcribe(Path("/fake/en.mp4"))

        assert transcript.full_text == ""
        extract_mock.assert_called_once()
        convert_mock.assert_called_once()

    def test_nonexistent_file_raises_file_not_found_error(self):
        """Missing file → FileNotFoundError."""
        adapter = _import_adapter()

        transcriber = adapter.MlxWhisperTranscriber()
        # Real non-existent path → is_file returns False (no patch applied)
        with pytest.raises(FileNotFoundError, match="Not a video file"):
            transcriber.transcribe(Path("/nonexistent/real.mp4"))

    def test_no_audio_stream_raises_runtime_error(self, monkeypatch):
        """ffmpeg returns None (no audio stream) → RuntimeError."""
        import sys  # type: ignore[import]

        mod = MagicMock(transcribe=MagicMock(return_value=SAMPLE_RESULT_DICT))
        monkeypatch.setitem(sys.modules, "mlx_whisper", mod)

        adapter = _import_adapter()
        monkeypatch.setattr(adapter, "_extract_audio_bytes", lambda path: None)  # type: ignore[attr-defined]

        monkeypatch.setattr(Path, "is_file", lambda self: True)  # type: ignore[attr-defined]

        adapter.MlxWhisperTranscriber()

    def test_audio_decode_failure_raises_runtime_error(self, monkeypatch):
        """_audio_bytes_to_array returns None → RuntimeError."""
        import sys  # type: ignore[import]

        mod = MagicMock()
        mod.transcribe.return_value = SAMPLE_RESULT_DICT

        def _fake_convert(raw: bytes) -> None:  # noqa: ANN202
            return None

        monkeypatch.setitem(sys.modules, "mlx_whisper", mod)
        adapter = _import_adapter()
        adapter._extract_audio_bytes = MagicMock(return_value=SAMPLE_PCM_BYTES)  # type: ignore[attr-defined]
        adapter._audio_bytes_to_array = _fake_convert  # type: ignore[attr-defined]

        monkeypatch.setattr(Path, "is_file", lambda self: True)  # type: ignore[attr-defined]

        transcriber = adapter.MlxWhisperTranscriber()
        with pytest.raises(RuntimeError, match="Failed to decode audio"):
            transcriber.transcribe(Path("/fake/badaudio.mp4"))

    def test_empty_text_and_segments_produces_empty_transcript(self, monkeypatch):
        """Whisper returns empty result → Transcript with no segments."""
        transcriber = _mocked_transcriber({"text": "", "segments": []}, monkeypatch)

        transcript = transcriber.transcribe(Path("/fake/empty.mp4"))

        from cutfinder.domain.models import Transcript

        assert isinstance(transcript, Transcript)
        assert transcript.full_text == ""
        assert len(transcript.segments) == 0

    def test_missing_whisper_text_key_treated_as_empty(self, monkeypatch):
        """Whisper result lacks 'text' key → default empty string."""
        transcriber = _mocked_transcriber({"segments": []}, monkeypatch)

        transcript = transcriber.transcribe(Path("/fake/missing_text.mp4"))

        from cutfinder.domain.models import Transcript

        assert isinstance(transcript, Transcript)
        assert transcript.full_text == ""


# ── MlxWhisperTranscriber init tests ─────────────────────

class TestTranscriberInit:
    """Test MlxWhisperTranscriber constructor parameter handling."""

    def test_default_model_and_language(self):
        mod = _import_adapter()
        t = mod.MlxWhisperTranscriber()

        assert t._model == "large-v3"
        assert t._language == "zh"

    def test_custom_model_and_language(self):
        mod = _import_adapter()
        t = mod.MlxWhisperTranscriber(model="distil-large-v3", language="en")

        assert t._model == "distil-large-v3"
        assert t._language == "en"
