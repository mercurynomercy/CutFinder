"""Unit tests for idle model-unload hooks (whisper + demucs).

Covers releasing the in-process models so they stop occupying RAM once
the work queue drains (see WorkerQueue.on_idle wiring in api.app).
"""

import sys
import types

import pytest

from cutfinder.adapters.demucs_separator import DemucsSeparator
from cutfinder.adapters.mlx_whisper import MlxWhisperTranscriber


# ── Whisper (process-global ModelHolder cache) ─────────────────────
#
# unload_cache() imports mlx.core + mlx_whisper.transcribe internally. The
# real import chain pulls in scipy/torch, which is brittle under the full
# suite (other tests leave module mocks in sys.modules). Inject lightweight
# fakes so we test unload_cache's logic in isolation.

def _install_fake_mlx(monkeypatch: pytest.MonkeyPatch, *, model: object | None) -> type:
    """Install fake mlx.core + mlx_whisper.transcribe; return the ModelHolder."""
    cleared: list[bool] = []
    fake_mx = types.ModuleType("mlx.core")
    fake_mx.clear_cache = lambda: cleared.append(True)  # type: ignore[attr-defined]
    fake_mlx = types.ModuleType("mlx")
    fake_mlx.core = fake_mx  # type: ignore[attr-defined]

    class ModelHolder:
        pass

    ModelHolder.model = model  # type: ignore[attr-defined]
    ModelHolder.model_path = "some/path" if model is not None else None  # type: ignore[attr-defined]
    ModelHolder.cleared = cleared  # type: ignore[attr-defined] — expose for assertions

    fake_tr = types.ModuleType("mlx_whisper.transcribe")
    fake_tr.ModelHolder = ModelHolder  # type: ignore[attr-defined]
    fake_pkg = types.ModuleType("mlx_whisper")
    fake_pkg.transcribe = fake_tr  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "mlx", fake_mlx)
    monkeypatch.setitem(sys.modules, "mlx.core", fake_mx)
    monkeypatch.setitem(sys.modules, "mlx_whisper", fake_pkg)
    monkeypatch.setitem(sys.modules, "mlx_whisper.transcribe", fake_tr)
    return ModelHolder


def test_whisper_unload_cache_resets_model_holder(monkeypatch: pytest.MonkeyPatch) -> None:
    """unload_cache() clears mlx-whisper's class-level model singleton + cache."""
    holder = _install_fake_mlx(monkeypatch, model=object())

    MlxWhisperTranscriber.unload_cache()

    assert holder.model is None  # type: ignore[attr-defined]
    assert holder.model_path is None  # type: ignore[attr-defined]
    assert holder.cleared == [True]  # type: ignore[attr-defined] — mx.clear_cache() called


def test_whisper_unload_cache_is_safe_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """unload_cache() is a no-op (no error) when nothing is loaded."""
    holder = _install_fake_mlx(monkeypatch, model=None)

    MlxWhisperTranscriber.unload_cache()  # must not raise

    assert holder.model is None  # type: ignore[attr-defined]


# ── Demucs (per-instance cached model) ─────────────────────────────

def test_demucs_unload_drops_cached_model() -> None:
    """unload() releases the cached Demucs model reference."""
    sep = DemucsSeparator()
    sep._dmodel = object()  # simulate a loaded model

    sep.unload()

    assert sep._dmodel is None


def test_demucs_unload_is_noop_when_not_loaded() -> None:
    """unload() does nothing (no error) when no model is loaded."""
    sep = DemucsSeparator()
    assert sep._dmodel is None

    sep.unload()  # must not raise

    assert sep._dmodel is None
