import time
import uuid

from nexus.core.intake import accept_work
from nexus.operator.queries import (
    get_attempts,
    get_recent_events,
    get_work_item,
    get_work_timeline,
)
from nexus.storage.database import connect, initialize


def get_state(work_id):
    connection = connect()

    try:
        row = connection.execute(
            """
            SELECT
                id,
                status,
                attempt_count,
                max_attempts,
                worker_id,
                release_id,
                last_error,
                final_reason
            FROM work_items
            WHERE id = ?
            """,
            (work_id,),
        ).fetchone()

        return dict(row) if row else None

    finally:
        connection.close()


def seed_diagnosis_history(work_id):
    """
    Create a deterministic work history containing:

    ACCEPTED
        ->
    FAILED
        ->
    RETRY
        ->
    SUCCEEDED

    This gives the operator a complete incident story to inspect.
    """

    connection = connect()

    try:
        now = time.time()

        connection.execute("BEGIN IMMEDIATE")

        connection.execute(
            """
            INSERT INTO work_items (
                id,
                type,
                body_json,
                status,
                attempt_count,
                max_attempts,
                created_at,
                updated_at,
                next_attempt_at,
                worker_id,
                release_id,
                accepted_at,
                completed_at,
                last_error,
                final_reason
            )
            VALUES (
                ?,
                'diagnosis-demo',
                ?,
                'SUCCEEDED',
                2,
                5,
                ?,
                ?,
                ?,
                ?,
                NULL,
                ?,
                ?,
                NULL,
                'processed_successfully'
            )
            """,
            (
                work_id,
                '{"message":"R12 diagnosis test"}',
                now - 5,
                now,
                now,
                "diagnosis-worker",
                now - 5,
                now,
            ),
        )

        connection.execute(
            """
            INSERT INTO dedupe_records (
                work_id,
                first_seen_at,
                completed_at,
                result_hash,
                status
            )
            VALUES (
                ?,
                ?,
                ?,
                NULL,
                'COMPLETED'
            )
            """,
            (
                work_id,
                now - 5,
                now,
            ),
        )

        connection.execute(
            """
            INSERT INTO attempts (
                work_id,
                attempt_number,
                worker_id,
                started_at,
                finished_at,
                outcome,
                error,
                release_id
            )
            VALUES (
                ?,
                1,
                'diagnosis-worker',
                ?,
                ?,
                'FAILED',
                'Simulated transient failure',
                NULL
            )
            """,
            (
                work_id,
                now - 4,
                now - 3,
            ),
        )

        connection.execute(
            """
            INSERT INTO attempts (
                work_id,
                attempt_number,
                worker_id,
                started_at,
                finished_at,
                outcome,
                error,
                release_id
            )
            VALUES (
                ?,
                2,
                'diagnosis-worker',
                ?,
                ?,
                'SUCCEEDED',
                NULL,
                NULL
            )
            """,
            (
                work_id,
                now - 2,
                now - 1,
            ),
        )

        events = [
            (
                "WORK_ACCEPTED",
                "ACCEPT",
                "durable_write",
                "Work accepted",
            ),
            (
                "WORK_STARTED",
                "CLAIM",
                "dispatcher_assignment",
                "Attempt 1 started",
            ),
            (
                "WORK_FAILED_RETRYING",
                "RETRY",
                "retryable_failure",
                "Attempt 1 failed; retry scheduled",
            ),
            (
                "WORK_STARTED",
                "CLAIM",
                "dispatcher_assignment",
                "Attempt 2 started",
            ),
            (
                "WORK_SUCCEEDED",
                "COMPLETE",
                "processing_success",
                "Work completed successfully",
            ),
        ]

        for event_type, decision, reason, message in events:

            connection.execute(
                """
                INSERT INTO events (
                    event_id,
                    occurred_at,
                    event_type,
                    subject_type,
                    subject_id,
                    work_id,
                    worker_id,
                    release_id,
                    incident_id,
                    severity,
                    decision,
                    reason,
                    before_json,
                    after_json,
                    message
                )
                VALUES (
                    lower(hex(randomblob(16))),
                    ?,
                    ?,
                    'work',
                    ?,
                    ?,
                    'diagnosis-worker',
                    NULL,
                    NULL,
                    'INFO',
                    ?,
                    ?,
                    NULL,
                    NULL,
                    ?
                )
                """,
                (
                    now,
                    event_type,
                    work_id,
                    work_id,
                    decision,
                    reason,
                    message,
                ),
            )

        connection.execute("COMMIT")

    except Exception:
        connection.execute("ROLLBACK")
        raise

    finally:
        connection.close()


def main():
    print("=== NEXUS R12 OPERATOR DIAGNOSIS TEST ===")

    initialize()

    work_id = (
        f"r12-diagnosis-{uuid.uuid4().hex[:8]}"
    )

    seed_diagnosis_history(work_id)

    start = time.time()

    # --------------------------------------------------------
    # STEP 1: Find the work item
    # --------------------------------------------------------

    work = get_work_item(work_id)

    assert work is not None

    print()
    print("Work:")
    print(work)

    # --------------------------------------------------------
    # STEP 2: Determine current state
    # --------------------------------------------------------

    state = get_state(work_id)

    assert state is not None
    assert state["status"] == "SUCCEEDED"
    assert state["attempt_count"] == 2

    print()
    print("Current state:")
    print(state)

    # --------------------------------------------------------
    # STEP 3: Inspect attempts
    # --------------------------------------------------------

    attempts = get_attempts(work_id)

    assert len(attempts) == 2

    failed_attempts = [
        attempt
        for attempt in attempts
        if attempt["outcome"] == "FAILED"
    ]

    successful_attempts = [
        attempt
        for attempt in attempts
        if attempt["outcome"] == "SUCCEEDED"
    ]

    assert len(failed_attempts) == 1
    assert len(successful_attempts) == 1

    print()
    print("Attempts:")

    for attempt in attempts:
        print(attempt)

    # --------------------------------------------------------
    # STEP 4: Inspect event timeline
    # --------------------------------------------------------

    timeline = get_work_timeline(work_id)

    assert len(timeline) >= 5

    event_types = [
        event["event_type"]
        for event in timeline
    ]

    assert "WORK_ACCEPTED" in event_types
    assert "WORK_STARTED" in event_types
    assert "WORK_FAILED_RETRYING" in event_types
    assert "WORK_SUCCEEDED" in event_types

    print()
    print("Timeline:")

    for event in timeline:
        print(
            event["event_type"],
            "|",
            event.get("decision"),
            "|",
            event.get("reason"),
            "|",
            event.get("message"),
        )

    # --------------------------------------------------------
    # STEP 5: Construct operator diagnosis
    # --------------------------------------------------------

    diagnosis = {
        "work_id": work_id,
        "final_status": state["status"],
        "attempts": state["attempt_count"],
        "failure_count": len(failed_attempts),
        "successful_attempts": len(
            successful_attempts
        ),
        "failure_reason": failed_attempts[0]["error"],
        "recovered": (
            state["status"] == "SUCCEEDED"
            and len(successful_attempts) > 0
        ),
    }

    print()
    print("Operator diagnosis:")
    print(diagnosis)

    assert diagnosis["final_status"] == "SUCCEEDED"
    assert diagnosis["attempts"] == 2
    assert diagnosis["failure_count"] == 1
    assert diagnosis["successful_attempts"] == 1
    assert diagnosis["recovered"] is True

    elapsed = time.time() - start

    print()
    print(
        f"Diagnosis reconstruction time: "
        f"{elapsed:.3f}s"
    )

    assert elapsed < 90, (
        "Operator diagnosis took longer than 90 seconds"
    )

    print()
    print("===================================")
    print("R12 OPERATOR DIAGNOSIS TEST PASSED")
    print("===================================")


if __name__ == "__main__":
    main()