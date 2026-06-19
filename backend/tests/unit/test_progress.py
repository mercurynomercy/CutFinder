"""Tests for :func:`cutfinder.adapters._progress.patch_tqdm`."""

from __future__ import annotations

import io
import types

import pytest
from tqdm import tqdm as _RealTqdm

from cutfinder.adapters._progress import patch_tqdm


def _fake_module() -> types.ModuleType:
    """A module-like object that imported the real tqdm package."""
    mod = types.ModuleType("fake_target")
    import tqdm as _tqdm_pkg

    mod.tqdm = _tqdm_pkg  # mirrors `import tqdm` in the target module
    return mod


def test_update_reports_fractions() -> None:
    mod = _fake_module()
    seen: list[float] = []
    with patch_tqdm(mod, seen.append):
        bar = mod.tqdm.tqdm(total=10, file=io.StringIO())
        bar.update(5)
        bar.update(5)
    assert seen == [0.5, 1.0]


def test_iterable_wrapping_reports_fractions() -> None:
    mod = _fake_module()
    seen: list[float] = []
    with patch_tqdm(mod, seen.append):
        # mininterval=0 forces tqdm to call update() each iteration (in real
        # demucs usage the per-iteration work is slow enough to clear the
        # default display interval naturally).
        for _ in mod.tqdm.tqdm(range(4), file=io.StringIO(), mininterval=0):
            pass
    # tqdm advances on each iteration → 0.25, 0.5, 0.75, 1.0
    assert seen == [0.25, 0.5, 0.75, 1.0]


def test_module_restored_after_normal_exit() -> None:
    mod = _fake_module()
    original = mod.tqdm
    with patch_tqdm(mod, lambda _f: None):
        assert mod.tqdm is not original
    assert mod.tqdm is original


def test_module_restored_after_exception() -> None:
    mod = _fake_module()
    original = mod.tqdm
    with pytest.raises(ValueError, match="boom"):
        with patch_tqdm(mod, lambda _f: None):
            raise ValueError("boom")
    assert mod.tqdm is original


def test_throwing_callback_does_not_propagate() -> None:
    mod = _fake_module()

    def _boom(_f: float) -> None:
        raise RuntimeError("callback boom")

    with patch_tqdm(mod, _boom):
        bar = mod.tqdm.tqdm(total=2, file=io.StringIO())
        bar.update(1)  # must not raise
        bar.update(1)


def test_shim_delegates_other_attributes() -> None:
    mod = _fake_module()
    with patch_tqdm(mod, lambda _f: None):
        # Non-`.tqdm` attribute access falls through to the real package.
        assert mod.tqdm.tqdm.__mro__[1] is _RealTqdm
        # e.g. tqdm.trange exists on the real package
        assert hasattr(mod.tqdm, "trange")
