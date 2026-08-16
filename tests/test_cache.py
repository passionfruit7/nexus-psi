import time

from nexus.core.cache_manager import (
    CacheExpiredError,
    CacheManager,
)


def main():
    print("=== NEXUS R9 CACHE FRESHNESS TEST ===")

    cache = CacheManager()

    # --------------------------------------------------
    # TEST 1: Cached value carries its age
    # --------------------------------------------------

    print()
    print("=== TEST 1: CACHE VALUE CARRIES AGE ===")

    cache.set(
        "service-status",
        "HEALTHY",
    )

    result = cache.inspect(
        "service-status"
    )

    print("Cached value:")
    print(result)

    assert result is not None
    assert result["value"] == "HEALTHY"
    assert "created_at" in result
    assert "age_seconds" in result

    assert result["age_seconds"] >= 0

    print(
        f"Age: "
        f"{result['age_seconds']:.6f}s"
    )

    print(
        "CACHE AGE TRACKING PASSED"
    )

    # --------------------------------------------------
    # TEST 2: Fresh value can be served
    # --------------------------------------------------

    print()
    print("=== TEST 2: FRESH VALUE IS SERVED ===")

    result = cache.get(
        "service-status",
        max_age_seconds=5,
    )

    print(result)

    assert result["available"] is True
    assert result["served"] is True
    assert result["reason"] == "fresh"
    assert result["value"] == "HEALTHY"
    assert result["age_seconds"] <= 5

    print(
        "FRESH CACHE SERVING PASSED"
    )

    # --------------------------------------------------
    # TEST 3: Expired value is refused
    # --------------------------------------------------

    print()
    print("=== TEST 3: EXPIRED VALUE IS REFUSED ===")

    cache.set(
        "short-lived",
        "OLD-VALUE",
    )

    # Give the cached value a measurable age.
    time.sleep(0.05)

    inspection = cache.inspect(
        "short-lived"
    )

    print("Before expiration:")
    print(inspection)

    assert inspection is not None
    assert inspection["age_seconds"] >= 0.05

    try:
        cache.get(
            "short-lived",
            max_age_seconds=0.01,
        )

        raise AssertionError(
            "Expired cache value was served"
        )

    except CacheExpiredError as error:
        print(
            "Correctly refused expired value:"
        )
        print(error)

    # --------------------------------------------------
    # TEST 4: Expired value remains inspectable
    # --------------------------------------------------

    print()
    print(
        "=== TEST 4: EXPIRED VALUE REMAINS VISIBLE ==="
    )

    expired = cache.inspect(
        "short-lived"
    )

    print(expired)

    assert expired is not None
    assert expired["value"] == "OLD-VALUE"
    assert expired["age_seconds"] > 0

    print(
        "Expired value remains observable "
        "without being served."
    )

    print()
    print("===================================")
    print("R9 CACHE FRESHNESS TEST PASSED")
    print("===================================")


if __name__ == "__main__":
    main()