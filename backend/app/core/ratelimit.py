"""Ограничение частоты действий. Счётчики хранятся в памяти процесса: этого достаточно для одного
экземпляра приложения, при нескольких экземплярах их нужно вынести в общее хранилище (Redis)."""

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float):
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _fresh(self, key: str, now: float) -> deque[float]:
        hits = self._hits[key]
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        return hits

    def allow(self, key: str) -> bool:
        """Засчитывает действие; False — лимит за окно исчерпан."""
        now = time.monotonic()
        with self._lock:
            hits = self._fresh(key, now)
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True

    def blocked(self, key: str) -> bool:
        """Исчерпан ли лимит; действие не засчитывается."""
        with self._lock:
            return len(self._fresh(key, time.monotonic())) >= self.limit

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
