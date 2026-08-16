import time

from nexus.services.cache_store import CacheStore


class CacheExpiredError(Exception):
    """Raised when cached data is older than the allowed limit."""


class CacheManager:
    """
    Cache manager that tracks the age of every cached value
    and refuses to serve expired values.
    """

    def __init__(self, store=None):
        self.store = store or CacheStore()

    def set(self, key, value):
        """Store a value together with its creation timestamp."""
        return self.store.put(key, value)

    def get(self, key, *, max_age_seconds):
        """
        Return a cached value only when it is within the
        permitted freshness window.
        """

        if max_age_seconds < 0:
            raise ValueError(
                "max_age_seconds must be non-negative"
            )

        cached = self.store.get(key)

        if cached is None:
            return {
                "available": False,
                "served": False,
                "key": key,
                "reason": "cache_miss",
            }

        now = time.time()

        age_seconds = (
            now - cached["created_at"]
        )

        result = {
            "available": True,
            "served": False,
            "key": key,
            "value": cached["value"],
            "created_at": cached["created_at"],
            "age_seconds": age_seconds,
            "max_age_seconds": max_age_seconds,
        }

        if age_seconds > max_age_seconds:
            result["reason"] = "cache_expired"

            raise CacheExpiredError(
                f"Cached value for {key} is "
                f"{age_seconds:.3f}s old; "
                f"maximum allowed age is "
                f"{max_age_seconds:.3f}s"
            )

        result["served"] = True
        result["reason"] = "fresh"

        return result

    def inspect(self, key):
        """
        Inspect a cached value without serving it.
        Expired values remain visible for diagnosis.
        """

        cached = self.store.get(key)

        if cached is None:
            return None

        age_seconds = (
            time.time()
            - cached["created_at"]
        )

        return {
            "key": key,
            "value": cached["value"],
            "created_at": cached["created_at"],
            "age_seconds": age_seconds,
        }
