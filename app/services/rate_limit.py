"""Small in-memory sliding-window rate limiter (single-server deployments)."""

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Request


class RateLimiter:
    def __init__(self, max_events: int, window_seconds: int):
        self.max_events = max_events
        self.window = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        q = self._events[key]
        while q and q[0] <= now - self.window:
            q.popleft()
        if not q:
            self._events.pop(key, None)
            q = self._events[key]
        return q

    def is_limited(self, key: str) -> bool:
        with self._lock:
            return len(self._prune(key, time.monotonic())) >= self.max_events

    def hit(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            self._prune(key, now).append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)


def client_ip(request: Request) -> str:
    # uvicorn applies X-Forwarded-For from trusted proxies (Caddy on 127.0.0.1)
    return request.client.host if request.client else "unknown"


# 5 failed logins per IP (or per username) in 15 minutes → locked out for the rest of the window
login_failures = RateLimiter(max_events=5, window_seconds=15 * 60)

# 10 guest submissions per IP per hour (a family on one WiFi still fits)
guest_submissions = RateLimiter(max_events=10, window_seconds=60 * 60)

# ID photo quality checks (guests may retake a few photos)
id_photo_checks = RateLimiter(max_events=40, window_seconds=60 * 60)
