import time
import uuid

from nexus.core.consistency import (
    check_consistency,
)
from nexus.storage.database import (
    connect,
    initialize,
)


def get_disagreement_events(subject_id):
    connection = connect()

    try:
        rows = connection.execute(
            """
            SELECT
                event_type,
                subject_type,
                subject_id,
                severity,
                decision,
                reason,
                before_json,
                after_json,
                message,
                occurred_at
            FROM events
            WHERE subject_id = ?
              AND event_type = 'CONSISTENCY_DISAGREEMENT'
            ORDER BY occurred_at ASC
            """,
            (subject_id,),
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


def main():
    print("=== NEXUS R8 CONSISTENCY TEST ===")

    initialize()

    subject_id = (
        f"r8-consistency-{uuid.uuid4().hex[:8]}"
    )

    print()
    print("Checking matching values...")

    result = check_consistency(
        "demo_state",
        subject_id,
        "HEALTHY",
        "HEALTHY",
        left_source="worker",
        right_source="operator",
    )

    print(result)

    assert result["consistent"] is True
    assert result["disagreement"] is False

    print("CONSISTENT VALUES PASSED")

    print()
    print("Checking conflicting values...")

    start = time.time()

    result = check_consistency(
        "demo_state",
        subject_id,
        "HEALTHY",
        "DEGRADED",
        left_source="worker",
        right_source="operator",
        detection_limit_seconds=5.0,
    )

    elapsed = time.time() - start

    print(result)

    assert result["consistent"] is False
    assert result["disagreement"] is True
    assert result["reported"] is True

    assert elapsed <= 5.0, (
        "Disagreement was not detected within "
        "the stated detection limit"
    )

    print(
        f"Disagreement detected in "
        f"{elapsed:.6f}s"
    )

    print()
    print("Checking that NEXUS did NOT silently repair...")

    assert result["left_value"] == "HEALTHY"
    assert result["right_value"] == "DEGRADED"

    print(
        "Original conflicting values remain visible."
    )

    events = get_disagreement_events(
        subject_id
    )

    print()
    print("Recorded disagreement events:")

    for event in events:
        print(event)

    assert len(events) == 1

    event = events[0]

    assert (
        event["event_type"]
        == "CONSISTENCY_DISAGREEMENT"
    )

    assert event["severity"] == "ERROR"
    assert event["decision"] == "REPORT"
    assert event["reason"] == "value_mismatch"

    assert event["subject_id"] == subject_id

    print()
    print("Structured disagreement event verified.")

    print()
    print("===================================")
    print("R8 CONSISTENCY TEST PASSED")
    print("===================================")


if __name__ == "__main__":
    main()