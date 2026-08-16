class OrderError(Exception):
    """Raised when an ordering operation is invalid."""


def classify_sequence(records):
    """
    Classify ordering information without inferring order from
    display position.

    Each record may contain an explicit `sequence` value.

    Example:

        [
            {"id": "A", "sequence": 1},
            {"id": "B", "sequence": 2},
            {"id": "C"},
        ]

    A -> B has known order.

    C has unknown order because it has no explicit sequence.
    Its position in the list is NOT treated as evidence.
    """

    if not isinstance(records, list):
        raise OrderError(
            "records must be a list"
        )

    normalized = []

    for position, record in enumerate(records):
        if not isinstance(record, dict):
            raise OrderError(
                "each record must be a dictionary"
            )

        if "id" not in record:
            raise OrderError(
                "each record must contain an id"
            )

        sequence = record.get("sequence")

        normalized.append(
            {
                "id": record["id"],
                "display_position": position,
                "sequence": sequence,
                "order_known": sequence is not None,
            }
        )

    known = [
        item
        for item in normalized
        if item["order_known"]
    ]

    unknown = [
        item
        for item in normalized
        if not item["order_known"]
    ]

    known.sort(
        key=lambda item: item["sequence"]
    )

    known_relationships = []

    for index in range(len(known) - 1):
        current = known[index]
        following = known[index + 1]

        known_relationships.append(
            {
                "before": current["id"],
                "after": following["id"],
                "basis": "explicit_sequence",
                "order_known": True,
            }
        )

    unknown_adjacencies = []

    for index in range(len(normalized) - 1):
        current = normalized[index]
        following = normalized[index + 1]

        if (
            not current["order_known"]
            or not following["order_known"]
        ):
            unknown_adjacencies.append(
                {
                    "left": current["id"],
                    "right": following["id"],
                    "basis": "display_adjacency_only",
                    "order_known": False,
                }
            )

    return {
        "records": normalized,
        "known_order": known_relationships,
        "unknown_order": unknown_adjacencies,
    }


def order_between(
    first,
    second,
):
    """
    Determine the relationship between two records using only
    explicit sequence values.

    Returns UNKNOWN when either record lacks an explicit
    sequence value.
    """

    first_sequence = first.get("sequence")
    second_sequence = second.get("sequence")

    if (
        first_sequence is None
        or second_sequence is None
    ):
        return {
            "relationship": "UNKNOWN",
            "order_known": False,
            "basis": "insufficient_order_evidence",
        }

    if first_sequence < second_sequence:
        relationship = "BEFORE"
    elif first_sequence > second_sequence:
        relationship = "AFTER"
    else:
        relationship = "SAME_POSITION"

    return {
        "relationship": relationship,
        "order_known": True,
        "basis": "explicit_sequence",
    }
