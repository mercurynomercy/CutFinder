"""patch_tqdm — intercept a module's tqdm to forward fractional progress.

Both Demucs (``demucs.apply``) and mlx-whisper (``mlx_whisper.transcribe``)
report per-frame progress only through an internal tqdm bar printed to stderr;
neither exposes a progress callback. This context manager temporarily swaps the
``tqdm`` attribute the target module imported for a thin shim whose ``.tqdm``
is a :class:`tqdm.tqdm` subclass that reports ``n / total`` on every update.

The swap is restored in ``finally``. Safe under ``worker_concurrency=1``
(sequential processing), so only one patch is active at a time.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Iterator

from tqdm import tqdm as _RealTqdm  # type: ignore[import-untyped]


@contextmanager
def patch_tqdm(module: object, on_fraction: Callable[[float], None]) -> Iterator[None]:
    """Forward *module*'s tqdm progress to *on_fraction* as a 0..1 fraction.

    *module* is expected to have done ``import tqdm`` and call ``tqdm.tqdm(...)``.
    While the context is active, ``module.tqdm`` is replaced by a shim that
    delegates every attribute to the real tqdm package except ``.tqdm``, which
    is a subclass reporting fractional progress. The original is restored on
    exit, even when the wrapped code raises.
    """
    real = module.tqdm  # type: ignore[attr-defined]  # the tqdm PACKAGE

    class _Reporter(_RealTqdm):  # type: ignore[misc]  # tqdm.tqdm is untyped
        def update(self, n: float = 1) -> bool | None:  # noqa: ANN001
            updated: bool | None = super().update(n)
            if self.total:
                try:
                    on_fraction(min(1.0, self.n / self.total))
                except Exception:  # noqa: BLE001 — UI callback must never break work
                    pass
            return updated

    class _Shim:
        tqdm = _Reporter

        def __getattr__(self, name: str) -> object:
            return getattr(real, name)

    module.tqdm = _Shim()  # type: ignore[attr-defined]
    try:
        yield
    finally:
        module.tqdm = real  # type: ignore[attr-defined]
