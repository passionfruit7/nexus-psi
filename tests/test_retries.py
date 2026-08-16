import time
import uuid

from nexus.core.intake import accept_work
from nexus.storage.database import connect, initialize
from nexus.workers.worker import claim_work, process_work


def get_work(work_id):
    connection = connect()

    try:
        row = connection.execute(
            """
            SELECT
                id,
                status,
                attempt_count,
                max_attempts,
                next_attempt_at,
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


def get_attempts(work_id):
    connection = connect()

    try:
        rows = connection.execute(
            """
            SELECT
                attempt_number,
                outcome,
                error
            FROM attempts
            WHERE work_id = ?
            ORDER BY attempt_number
            """,
            (work_id,),
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


def get_events(work_id):
    connection = connect()

    try:
        rows = connection.execute(
            """
            SELECT
                event_type,
                decision,
                reason
            FROM events
            WHERE work_id = ?
            ORDER BY id
            """,
            (work_id,),
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


def run_worker_once(worker_id):
    """
    Claim and process exactly one available work item.
    """

    connection = connect()

    try:
        work = claim_work(
            connection,
            worker_id,
        )

        if work is None:
            return None

        process_work(
            connection,
            worker_id,
            work,
        )

        return work

    finally:
        connection.close()


def wait_until_ready(work_id, timeout=10):
    """
    Wait until a retry becomes eligible for execution.
    """

    deadline = time.time() + timeout

    while time.time() < deadline:
        work = get_work(work_id)

        if work is None:
            raise AssertionError(
                f"Work {work_id} disappeared"
            )

        if (
            work["status"] == "QUEUED"
            and (
                work["next_attempt_at"] is None
                or work["next_attempt_at"] <= time.time()
            )
        ):
            return work

        time.sleep(0.1)

    raise AssertionError(
        f"Work {work_id} did not become "
        "ready for retry"
    )


def test_transient_failure_retries_then_succeeds():
    print()
    print(
        "=== TEST: TRANSIENT FAILURE → RETRY → SUCCESS ==="
    )

    work_id = (
        "retry-success-"
        + uuid.uuid4().hex[:8]
    )

    connection = connect()

    try:
        result = accept_work(
            connection,
            work_id,
            "demo",
            {
                "message": "Transient failure test",
                "fail_attempts": 2,
            },
            max_attempts=5,
        )

    finally:
        connection.close()

    assert result["accepted"] is True
    assert result["duplicate"] is False

    # Attempt 1.
    run_worker_once("retry-test-worker")

    work = get_work(work_id)

    print("After attempt 1:", work)

    assert work["status"] == "QUEUED"
    assert work["attempt_count"] == 1

    # Wait for retry backoff.
    wait_until_ready(work_id)

    # Attempt 2.
    run_worker_once("retry-test-worker")

    work = get_work(work_id)

    print("After attempt 2:", work)

    assert work["status"] == "QUEUED"
    assert work["attempt_count"] == 2

    # Wait for retry backoff.
    wait_until_ready(work_id)

    # Attempt 3 should succeed.
    run_worker_once("retry-test-worker")

    work = get_work(work_id)

    print("Final state:", work)

    assert work["status"] == "SUCCEEDED"
    assert work["attempt_count"] == 3

    attempts = get_attempts(work_id)

    print("Attempts:")

    for attempt in attempts:
        print(attempt)

    assert len(attempts) == 3
    assert attempts[0]["outcome"] == "FAILED"
    assert attempts[1]["outcome"] == "FAILED"
    assert attempts[2]["outcome"] == "SUCCEEDED"

    events = get_events(work_id)

    event_types = [
        event["event_type"]
        for event in events
    ]

    assert (
        event_types.count(
            "WORK_FAILED_RETRYING"
        )
        == 2
    )

    assert "WORK_SUCCEEDED" in event_types

    print(
        "TRANSIENT RETRY TEST PASSED"
    )


def test_retry_budget_exhaustion_dead_letters():
    print()
    print(
        "=== TEST: RETRY BUDGET → DEAD LETTER ==="
    )

    work_id = (
        "retry-dead-letter-"
        + uuid.uuid4().hex[:8]
    )

    connection = connect()

    try:
        result = accept_work(
            connection,
            work_id,
            "demo",
            {
                "message": "Permanent failure test",
                "always_fail": True,
            },
            max_attempts=3,
        )

    finally:
        connection.close()

    assert result["accepted"] is True
    assert result["duplicate"] is False

    # Attempt 1.
    run_worker_once(
        "dead-letter-test-worker"
    )

    work = get_work(work_id)

    print("After attempt 1:", work)

    assert work["status"] == "QUEUED"
    assert work["attempt_count"] == 1

    wait_until_ready(work_id)

    # Attempt 2.
    run_worker_once(
        "dead-letter-test-worker"
    )

    work = get_work(work_id)

    print("After attempt 2:", work)

    assert work["status"] == "QUEUED"
    assert work["attempt_count"] == 2

    wait_until_ready(work_id)

    # Attempt 3 must be terminal.
    run_worker_once(
        "dead-letter-test-worker"
    )

    work = get_work(work_id)

    print("Final state:", work)

    assert work["status"] == "DEAD_LETTERED"
    assert work["attempt_count"] == 3

    assert (
        work["final_reason"]
        == "max_attempts_exhausted"
    )

    attempts = get_attempts(work_id)

    print("Attempts:")

    for attempt in attempts:
        print(attempt)

    assert len(attempts) == 3

    assert all(
        attempt["outcome"] == "FAILED"
        for attempt in attempts
    )

    events = get_events(work_id)

    event_types = [
        event["event_type"]
        for event in events
    ]

    assert (
        event_types.count(
            "WORK_FAILED_RETRYING"
        )
        == 2
    )

    assert (
        "WORK_DEAD_LETTERED"
        in event_types
    )

    print(
        "DEAD-LETTER RETRY TEST PASSED"
    )


def main():
    initialize()

    test_transient_failure_retries_then_succeeds()

    test_retry_budget_exhaustion_dead_letters()

    print()
    print("===================================")
    print("ALL RETRY TESTS PASSED")
    print("===================================")


if __name__ == "__main__":
    main()