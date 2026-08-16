import uuid

from nexus.core.intake import accept_work
from nexus.storage.database import connect, initialize
from nexus.workers.worker import claim_work, process_work


def get_work(work_id):
    """
    Return the current work item.
    """

    connection = connect()

    try:
        row = connection.execute(
            """
            SELECT
                id,
                status,
                attempt_count,
                max_attempts,
                worker_id
            FROM work_items
            WHERE id = ?
            """,
            (work_id,),
        ).fetchone()

        return dict(row) if row else None

    finally:
        connection.close()


def count_work_items(work_id):
    """
    Count physical work_items rows for a logical work ID.
    """

    connection = connect()

    try:
        row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM work_items
            WHERE id = ?
            """,
            (work_id,),
        ).fetchone()

        return row["count"]

    finally:
        connection.close()


def count_attempts(work_id):
    """
    Count execution attempts for a work item.
    """

    connection = connect()

    try:
        row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM attempts
            WHERE work_id = ?
            """,
            (work_id,),
        ).fetchone()

        return row["count"]

    finally:
        connection.close()


def delete_test_work(work_id):
    """
    Remove a test-created work item and all of its
    dependent records.

    This is test cleanup only.

    Production NEXUS does not use this operation during
    normal work processing.
    """

    connection = connect()

    try:
        connection.execute("BEGIN IMMEDIATE")

        connection.execute(
            """
            DELETE FROM events
            WHERE work_id = ?
            """,
            (work_id,),
        )

        connection.execute(
            """
            DELETE FROM attempts
            WHERE work_id = ?
            """,
            (work_id,),
        )

        connection.execute(
            """
            DELETE FROM dedupe_records
            WHERE work_id = ?
            """,
            (work_id,),
        )

        connection.execute(
            """
            DELETE FROM work_items
            WHERE id = ?
            """,
            (work_id,),
        )

        connection.execute("COMMIT")

    except Exception:
        connection.execute("ROLLBACK")
        raise

    finally:
        connection.close()


def test_duplicate_before_execution():
    """
    Submit the same work ID twice before execution.

    Expected:

        First submission:
            accepted=True
            duplicate=False

        Second submission:
            accepted=True
            duplicate=True

        Database:
            exactly one work item
            zero execution attempts
    """

    print()
    print(
        "=== TEST 1: DUPLICATE BEFORE EXECUTION ==="
    )

    work_id = (
        "idempotency-before-"
        + uuid.uuid4().hex[:8]
    )

    try:
        connection = connect()

        try:
            first = accept_work(
                connection,
                work_id,
                "demo",
                {
                    "message": "Idempotency test",
                },
            )

        finally:
            connection.close()

        print("First submission:")
        print(first)

        assert first["accepted"] is True
        assert first["duplicate"] is False
        assert first["id"] == work_id
        assert first["status"] == "QUEUED"

        connection = connect()

        try:
            second = accept_work(
                connection,
                work_id,
                "demo",
                {
                    "message": (
                        "This must NOT create "
                        "another job"
                    ),
                },
            )

        finally:
            connection.close()

        print("Second submission:")
        print(second)

        assert second["accepted"] is True
        assert second["duplicate"] is True
        assert second["id"] == work_id
        assert second["status"] == "QUEUED"

        assert count_work_items(work_id) == 1
        assert count_attempts(work_id) == 0

        print(
            "DUPLICATE-BEFORE-EXECUTION "
            "TEST PASSED"
        )

    finally:
        delete_test_work(work_id)


def test_duplicate_while_running():
    """
    Submit the same work ID while the first execution
    is already RUNNING.

    Expected:

        original work
            ↓
        RUNNING

        duplicate submission
            ↓
        duplicate=True

        original work continues
            ↓
        SUCCEEDED

        total attempts = 1
    """

    print()
    print(
        "=== TEST 2: DUPLICATE WHILE RUNNING ==="
    )

    work_id = (
        "idempotency-running-"
        + uuid.uuid4().hex[:8]
    )

    try:
        connection = connect()

        try:
            first = accept_work(
                connection,
                work_id,
                "demo",
                {
                    "message": (
                        "Running idempotency test"
                    ),
                },
            )

        finally:
            connection.close()

        assert first["accepted"] is True
        assert first["duplicate"] is False

        # Explicitly claim THIS work item.
        #
        # This avoids older queued test jobs in the
        # database being accidentally claimed.
        connection = connect()

        try:
            work = claim_work(
                connection,
                "idempotency-worker",
                work_id=work_id,
            )

        finally:
            connection.close()

        assert work is not None
        assert work["id"] == work_id
        assert work["attempt_number"] == 1

        running = get_work(work_id)

        print("Original work:")
        print(running)

        assert running is not None
        assert running["status"] == "RUNNING"
        assert running["attempt_count"] == 1
        assert (
            running["worker_id"]
            == "idempotency-worker"
        )

        # Submit the same logical work while it is
        # already RUNNING.
        connection = connect()

        try:
            duplicate = accept_work(
                connection,
                work_id,
                "demo",
                {
                    "message": (
                        "Duplicate while running"
                    ),
                },
            )

        finally:
            connection.close()

        print("Duplicate submission:")
        print(duplicate)

        assert duplicate["accepted"] is True
        assert duplicate["duplicate"] is True
        assert duplicate["id"] == work_id
        assert duplicate["status"] == "RUNNING"

        # There must still be exactly one work item
        # and exactly one execution attempt.
        assert count_work_items(work_id) == 1
        assert count_attempts(work_id) == 1

        # Finish the original execution.
        #
        # This proves that the duplicate submission did
        # not interfere with the original work.
        connection = connect()

        try:
            process_work(
                connection,
                "idempotency-worker",
                work,
            )

        finally:
            connection.close()

        final_state = get_work(work_id)

        print("Final original work state:")
        print(final_state)

        assert final_state is not None
        assert final_state["status"] == "SUCCEEDED"
        assert final_state["attempt_count"] == 1
        assert (
            final_state["worker_id"]
            == "idempotency-worker"
        )

        # Still only one execution.
        assert count_work_items(work_id) == 1
        assert count_attempts(work_id) == 1

        print(
            "DUPLICATE-WHILE-RUNNING "
            "TEST PASSED"
        )

    finally:
        delete_test_work(work_id)


def test_duplicate_after_success():
    """
    Submit the same work ID after the original execution
    has already succeeded.

    Expected:

        original
            ↓
        SUCCEEDED

        duplicate submission
            ↓
        duplicate=True

        attempt count remains 1.
    """

    print()
    print(
        "=== TEST 3: DUPLICATE AFTER SUCCESS ==="
    )

    work_id = (
        "idempotency-after-"
        + uuid.uuid4().hex[:8]
    )

    try:
        connection = connect()

        try:
            first = accept_work(
                connection,
                work_id,
                "demo",
                {
                    "message": (
                        "Successful "
                        "idempotency test"
                    ),
                },
            )

        finally:
            connection.close()

        assert first["accepted"] is True
        assert first["duplicate"] is False

        # Explicitly claim THIS work item.
        connection = connect()

        try:
            work = claim_work(
                connection,
                "idempotency-success-worker",
                work_id=work_id,
            )

        finally:
            connection.close()

        assert work is not None
        assert work["id"] == work_id
        assert work["attempt_number"] == 1

        # Execute the original work exactly once.
        connection = connect()

        try:
            process_work(
                connection,
                "idempotency-success-worker",
                work,
            )

        finally:
            connection.close()

        completed = get_work(work_id)

        print("Completed work:")
        print(completed)

        assert completed is not None
        assert completed["status"] == "SUCCEEDED"
        assert completed["attempt_count"] == 1

        # Submit the same logical work again.
        connection = connect()

        try:
            duplicate = accept_work(
                connection,
                work_id,
                "demo",
                {
                    "message": (
                        "This must NOT "
                        "execute again"
                    ),
                },
            )

        finally:
            connection.close()

        print("Duplicate after success:")
        print(duplicate)

        assert duplicate["accepted"] is True
        assert duplicate["duplicate"] is True
        assert duplicate["id"] == work_id
        assert duplicate["status"] == "SUCCEEDED"

        # Most important assertion:
        # no second execution was created.
        assert count_work_items(work_id) == 1
        assert count_attempts(work_id) == 1

        final_state = get_work(work_id)

        assert final_state is not None
        assert final_state["status"] == "SUCCEEDED"
        assert final_state["attempt_count"] == 1

        print(
            "DUPLICATE-AFTER-SUCCESS "
            "TEST PASSED"
        )

    finally:
        delete_test_work(work_id)


def main():
    print("=== NEXUS IDEMPOTENCY TESTS ===")

    initialize()

    test_duplicate_before_execution()

    test_duplicate_while_running()

    test_duplicate_after_success()

    print()
    print("===================================")
    print("ALL IDEMPOTENCY TESTS PASSED")
    print("===================================")


if __name__ == "__main__":
    main()