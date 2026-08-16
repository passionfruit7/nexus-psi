from nexus.core.degradation import (
    DegradationManager,
)


def main():
    print("=== NEXUS R10 DEGRADATION TEST ===")

    manager = DegradationManager()

    # --------------------------------------------------
    # TEST 1: Dependency available
    # --------------------------------------------------

    print()
    print("=== TEST 1: HEALTHY DEPENDENCY ===")

    result = manager.resolve(
        lambda: {
            "inventory": 42,
            "source": "live",
        },
        fallback={
            "inventory": 0,
            "source": "fallback",
        },
    )

    print(result)

    assert result.status == "HEALTHY"
    assert result.dependency_available is True
    assert result.degraded is False
    assert result.value["inventory"] == 42

    print("HEALTHY DEPENDENCY PASSED")

    # --------------------------------------------------
    # TEST 2: Dependency unavailable
    # --------------------------------------------------

    print()
    print("=== TEST 2: DEPENDENCY UNAVAILABLE ===")

    def unavailable_dependency():
        raise ConnectionError(
            "inventory service unavailable"
        )

    result = manager.resolve(
        unavailable_dependency,
        fallback={
            "inventory": 40,
            "source": "last-known-value",
        },
    )

    print(result)

    assert result.status == "DEGRADED"
    assert result.dependency_available is False
    assert result.degraded is True

    assert (
        result.value["inventory"]
        == 40
    )

    print(
        "Fallback value returned:"
    )
    print(result.value)

    print(
        "Status:",
        result.status,
    )

    print(
        "Reason:",
        result.reason,
    )

    print("DEGRADED DEPENDENCY PASSED")

    # --------------------------------------------------
    # TEST 3: Never pretend fallback is healthy
    # --------------------------------------------------

    print()
    print(
        "=== TEST 3: NO FALSE HEALTH CLAIM ==="
    )

    assert result.status != "HEALTHY"
    assert result.degraded is True
    assert result.dependency_available is False

    print(
        "Fallback is explicitly marked DEGRADED."
    )

    # --------------------------------------------------
    # TEST 4: No fallback
    # --------------------------------------------------

    print()
    print(
        "=== TEST 4: DEPENDENCY UNAVAILABLE "
        "WITHOUT FALLBACK ==="
    )

    result = manager.resolve(
        unavailable_dependency,
    )

    print(result)

    assert result.status == "DEGRADED"
    assert result.degraded is True
    assert result.dependency_available is False
    assert result.value is None

    print(
        "Unavailable dependency remains "
        "explicitly visible."
    )

    print()
    print("===================================")
    print("R10 DEGRADATION TEST PASSED")
    print("===================================")


if __name__ == "__main__":
    main()
