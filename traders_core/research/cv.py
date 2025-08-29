from __future__ import annotations
import numpy as np
from typing import Iterator, Tuple

class PurgedKFold:
    """
    Time-aware CV: no look-ahead, with 'embargo' bars after each test block.
    """
    def __init__(self, n_splits: int = 5, embargo: int = 10):
        self.n_splits = n_splits
        self.embargo = max(0, int(embargo))

    def split(self, n: int) -> Iterator[Tuple[np.ndarray, np.ndarray]]:
        fold_sizes = np.full(self.n_splits, n // self.n_splits, dtype=int)
        fold_sizes[: n % self.n_splits] += 1
        indices = np.arange(n)
        current = 0
        for fold_size in fold_sizes:
            te_start, te_end = current, current + fold_size
            # purge = [te_start - embargo, te_end + embargo]
            tr_idx = indices.copy()
            lo = max(0, te_start - self.embargo)
            hi = min(n, te_end + self.embargo)
            mask = np.ones(n, dtype=bool)
            mask[lo:hi] = False
            tr = tr_idx[mask]
            te = indices[te_start:te_end]
            yield tr, te
            current = te_end
