"""Saf tablo fonksiyonları için girdiye göre önbellek (A-99).

Metrik formülleri (`kurgu_analytics.metrics`) saftır: aynı tablo aynı sonucu verir. Anahtar
tablonun içeriğinden (sütunlar, dizin, değerler) türetildiği için önbellek hiçbir zaman eski sonuç
dönmez; veri değişince anahtar da değişir. Süreç başına en çok `size` sonuç tutulur.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from collections.abc import Callable

import pandas as pd


def frame_key(frame: pd.DataFrame) -> str:
    digest = hashlib.blake2b(digest_size=20)
    digest.update(repr(list(frame.columns)).encode())
    digest.update(repr([str(t) for t in frame.dtypes]).encode())
    digest.update(pd.util.hash_pandas_object(frame, index=True).to_numpy().tobytes())
    return digest.hexdigest()


class FrameMemo:
    def __init__(self, fn: Callable[[pd.DataFrame], pd.DataFrame], size: int = 64) -> None:
        self.fn = fn
        self.size = size
        self.entries: OrderedDict[str, pd.DataFrame] = OrderedDict()

    def __call__(self, frame: pd.DataFrame) -> pd.DataFrame:
        key = frame_key(frame)
        if key in self.entries:
            self.entries.move_to_end(key)
        else:
            self.entries[key] = self.fn(frame)
            if len(self.entries) > self.size:
                self.entries.popitem(last=False)
        # Kopya döner: çağıran sonucu değiştirse bile önbellek bozulmaz.
        return self.entries[key].copy()
