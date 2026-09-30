"""インスタンス内で動く簡易のレート制限と1日の呼び出し上限。

Cloud Run の max-instances を小さくしているので、この程度でも費用の暴走を防げる。
永続化しない（個人データを保存しない方針）。
"""
from __future__ import annotations

import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, max_requests: int, window_sec: int, max_keys: int = 5000):
        self.max_requests = max_requests
        self.window = window_sec
        self.max_keys = max_keys
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, now: float | None = None) -> tuple[bool, int]:
        """(許可するか, 許可しない場合の待ち秒数)"""
        now = time.monotonic() if now is None else now
        if len(self._hits) > self.max_keys:
            self._gc(now)
        q = self._hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.max_requests:
            return False, max(1, int(self.window - (now - q[0])))
        q.append(now)
        return True, 0

    def _gc(self, now: float) -> None:
        for k in [k for k, q in self._hits.items() if not q or now - q[-1] > self.window]:
            del self._hits[k]
        if len(self._hits) > self.max_keys:  # それでも多ければ全消去（安全側）
            self._hits.clear()


class DailyBudget:
    """Gemini呼び出し回数の1日上限（UTC日付で切り替え）。"""

    def __init__(self, limit: int):
        self.limit = limit
        self._day = ""
        self._count = 0

    def take(self, n: int = 1) -> bool:
        day = time.strftime("%Y-%m-%d", time.gmtime())
        if day != self._day:
            self._day, self._count = day, 0
        if self._count + n > self.limit:
            return False
        self._count += n
        return True

    @property
    def used(self) -> int:
        return self._count
