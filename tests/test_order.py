from nexus.core.order import (
    classify_sequence,
    order_between,
)


def main():
    print("=== NEXUS R13 ORDER CERTAINTY TEST ===")

    # --------------------------------------------------
    # TEST 1: Explicit order is recognized
    # --------------------------------------------------

    print()
    print("=== TEST 1: EXPLICIT ORDER ===")

    records = [
        {
            "id": "record-A",
            "sequence": 10,
        },
        {
            "id": "record-B",
            "sequence": 20,
        },
        {
            "id": "record-C",
            "sequence": 30,
        },
    ]

    result = classify_sequence(records)

    print(result)

    assert len(result["known_order"]) == 2

    assert (
        result["known_order"][0]["before"]
        == "record-A"
    )

    assert (
        result["known_order"][0]["after"]
        == "record-B"
    )

    assert (
        result["known_order"][0]["order_known"]
        is True
    )

    print("EXPLICIT ORDER PASSED")

    # --------------------------------------------------
    # TEST 2: Display adjacency is NOT treated as order
    # --------------------------------------------------

    print()
    print(
        "=== TEST 2: DISPLAY ADJACENCY IS UNKNOWN ==="
    )

    records = [
        {
            "id": "record-X",
        },
        {
            "id": "record-Y",
        },
    ]

    result = classify_sequence(records)

    print(result)

    assert len(result["known_order"]) == 0
    assert len(result["unknown_order"]) == 1

    adjacency = result["unknown_order"][0]

    assert adjacency["left"] == "record-X"
    assert adjacency["right"] == "record-Y"

    assert (
        adjacency["order_known"]
        is False
    )

    assert (
        adjacency["basis"]
        == "display_adjacency_only"
    )

    print(
        "Adjacent records are correctly marked "
        "as UNKNOWN."
    )

    print("DISPLAY ADJACENCY TEST PASSED")

    # --------------------------------------------------
    # TEST 3: Partially known sequence
    # --------------------------------------------------

    print()
    print(
        "=== TEST 3: PARTIALLY KNOWN ORDER ==="
    )

    records = [
        {
            "id": "known-A",
            "sequence": 1,
        },
        {
            "id": "unknown-B",
        },
        {
            "id": "known-C",
            "sequence": 3,
        },
    ]

    result = classify_sequence(records)

    print(result)

    assert len(result["known_order"]) == 1

    assert (
        result["known_order"][0]["before"]
        == "known-A"
    )

    assert (
        result["known_order"][0]["after"]
        == "known-C"
    )

    assert len(result["unknown_order"]) == 2

    print(
        "Known and unknown ordering information "
        "correctly separated."
    )

    print(
        "PARTIAL ORDER TEST PASSED"
    )

    # --------------------------------------------------
    # TEST 4: Pairwise check refuses to guess
    # --------------------------------------------------

    print()
    print(
        "=== TEST 4: NO ORDER GUESSING ==="
    )

    first = {
        "id": "first",
    }

    second = {
        "id": "second",
    }

    relationship = order_between(
        first,
        second,
    )

    print(relationship)

    assert (
        relationship["relationship"]
        == "UNKNOWN"
    )

    assert (
        relationship["order_known"]
        is False
    )

    assert (
        relationship["basis"]
        == "insufficient_order_evidence"
    )

    print(
        "NEXUS refuses to infer order from "
        "missing evidence."
    )

    print("NO ORDER GUESSING TEST PASSED")

    # --------------------------------------------------
    # FINAL
    # --------------------------------------------------

    print()
    print("===================================")
    print("R13 ORDER CERTAINTY TEST PASSED")
    print("===================================")


if __name__ == "__main__":
    main()
