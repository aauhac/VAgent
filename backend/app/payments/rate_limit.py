"""In-memory rate limit for single-replica deployments. Fail closed on grant if over limit."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

_LOCK = Lock()
_HITS: dict[str, deque[float]] = defaultdict(deque)

# Per authenticated user (and optional IP) — payment endpoints only.
WINDOW_SECONDS = 60
MAX_HITS = 30


def reset() -> None:
    """Drop all buckets. Test seam: the window is process-global, so a suite that logs
    in many times would otherwise spend another suite's budget."""
    with _LOCK:
        _HITS.clear()


def allow(key: str, *, max_hits: int = MAX_HITS, window: int = WINDOW_SECONDS) -> bool:
    now = time.time()
    with _LOCK:
        bucket = _HITS[key]
        while bucket and now - bucket[0] > window:
            bucket.popleft()
        if len(bucket) >= max_hits:
            return False
        bucket.append(now)
        return True
