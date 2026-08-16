import uuid

from nexus.core.intake import accept_work
from nexus.core.supervisor import Supervisor
from nexus.operator.commands import (
    OperatorCommandError,
    restart_worker,
    requeue_work,
    retry_dead_letter,
    start_worker,
    stop_worker,
)
from nexus.operator.queries import (
    get_work_item,
    get_work_timeline,
)
from nexus.storage.database import connect, initialize


def delete_test_work(work_id):
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


def create_dead_letter_work(work_id):
    """
    Create a deterministic DEAD_LETTERED item for testing
    the operator requeue command.
    """

    connection = connect()

    try:
        connection.execute("BEGIN IMMEDIATE")

        now = 1000.0

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
                'operator-test',
                '{}',
                'DEAD_LETTERED',
                3,
                3,
                ?,
                ?,
                ?,
                NULL,
                NULL,
                ?,
                NULL,
                'test_failure',
                'max_attempts_exhausted'
            )
            """,
            (
                work_id,
                now,
                now,
                now,
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
                NULL,
                NULL,
                'PROCESSING'
            )
            """,
            (
                work_id,
                now,
            ),
        )

        connection.execute("COMMIT")

    except Exception:
        connection.execute("ROLLBACK")
        raise

    finally:
        connection.close()


def main():
    print("=== NEXUS OPERATOR COMMAND TEST ===")

    initialize()

    supervisor = Supervisor(
        [
            "operator-command-worker",
        ]
    )

    work_id = (
        "operator-command-"
        + uuid.uuid4().hex[:8]
    )

    dead_letter_id = (
        "operator-dead-letter-"
        + uuid.uuid4().hex[:8]
    )

    try:
        # =============================================
        # WORKER START
        # =============================================

        result = start_worker(
            supervisor,
            "operator-command-worker",
        )

        print()
        print("Start worker:")
        print(result)

        assert result["success"] is True
        assert result["state"] == "RUNNING"

        # =============================================
        # STARTING AGAIN MUST FAIL
        # =============================================

        try:
            start_worker(
                supervisor,
                "operator-command-worker",
            )

            raise AssertionError(
                "Starting an already-running worker "
                "should have failed"
            )

        except OperatorCommandError:
            print(
                "Duplicate worker start correctly rejected"
            )

        # =============================================
        # RESTART WORKER
        # =============================================

        result = restart_worker(
            supervisor,
            "operator-command-worker",
        )

        print()
        print("Restart worker:")
        print(result)

        assert result["success"] is True
        assert result["state"] == "RUNNING"

        # =============================================
        # STOP WORKER
        # =============================================

        result = stop_worker(
            supervisor,
            "operator-command-worker",
        )

        print()
        print("Stop worker:")
        print(result)

        assert result["success"] is True
        assert result["state"] == "STOPPED"

        # =============================================
        # STOPPING AGAIN MUST FAIL
        # =============================================

        try:
            stop_worker(
                supervisor,
                "operator-command-worker",
            )

            raise AssertionError(
                "Stopping an already-stopped worker "
                "should have failed"
            )

        except OperatorCommandError:
            print(
                "Duplicate worker stop correctly rejected"
            )

        # =============================================
        # CREATE WORK
        # =============================================

        connection = connect()

        try:
            accepted = accept_work(
                connection,
                work_id,
                "operator-test",
                {
                    "message": (
                        "Operator command test"
                    ),
                },
            )

        finally:
            connection.close()

        print()
        print("Accepted work:")
        print(accepted)

        assert accepted["accepted"] is True

        # =============================================
        # NORMAL QUEUED WORK CANNOT BE REQUEUED
        # =============================================

        try:
            requeue_work(work_id)

            raise AssertionError(
                "QUEUED work should not be "
                "requeued"
            )

        except OperatorCommandError:
            print(
                "Invalid QUEUED → QUEUED command "
                "correctly rejected"
            )

        # =============================================
        # SUCCEEDED WORK CANNOT BE REQUEUED
        # =============================================

        connection = connect()

        try:
            connection.execute(
                """
                UPDATE work_items
                SET
                    status = 'SUCCEEDED',
                    completed_at = ?,
                    updated_at = ?,
                    final_reason = ?
                WHERE id = ?
                """,
                (
                    1001.0,
                    1001.0,
                    "test_success",
                    work_id,
                ),
            )

        finally:
            connection.close()

        try:
            requeue_work(work_id)

            raise AssertionError(
                "SUCCEEDED work should not be "
                "requeued"
            )

        except OperatorCommandError:
            print(
                "Invalid SUCCEEDED → QUEUED command "
                "correctly rejected"
            )

        # =============================================
        # CREATE DEAD LETTER WORK
        # =============================================

        create_dead_letter_work(
            dead_letter_id
        )

        dead_letter = get_work_item(
            dead_letter_id
        )

        print()
        print("Dead-letter work:")
        print(dead_letter)

        assert (
            dead_letter["status"]
            == "DEAD_LETTERED"
        )

        # =============================================
        # REQUEUE DEAD LETTER
        # =============================================

        result = requeue_work(
            dead_letter_id
        )

        print()
        print("Requeue dead-letter:")
        print(result)

        assert result["success"] is True
        assert (
            result["previous_status"]
            == "DEAD_LETTERED"
        )
        assert result["status"] == "QUEUED"

        requeued = get_work_item(
            dead_letter_id
        )

        print()
        print("After requeue:")
        print(requeued)

        assert requeued["status"] == "QUEUED"
        assert requeued["worker_id"] is None
        assert requeued["final_reason"] is None

        # =============================================
        # RETRY DEAD LETTER COMMAND
        # =============================================

        connection = connect()

        try:
            connection.execute(
                """
                UPDATE work_items
                SET
                    status = 'DEAD_LETTERED',
                    final_reason = 'max_attempts_exhausted',
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    1002.0,
                    dead_letter_id,
                ),
            )

        finally:
            connection.close()

        result = retry_dead_letter(
            dead_letter_id
        )

        print()
        print("Retry dead-letter:")
        print(result)

        assert result["success"] is True
        assert (
            result["command"]
            == "retry_dead_letter"
        )
        assert result["status"] == "QUEUED"

        # =============================================
        # VERIFY OPERATOR EVENTS
        # =============================================

        timeline = get_work_timeline(
            dead_letter_id
        )

        print()
        print("Dead-letter timeline:")

        for event in timeline:
            print(event)

        event_types = [
            event["event_type"]
            for event in timeline
        ]

        assert (
            "OPERATOR_WORK_REQUEUED"
            in event_types
        )

        print()
        print("===================================")
        print("OPERATOR COMMAND TEST PASSED")
        print("===================================")

    finally:
        supervisor.running = False
        supervisor.stop_all()

        delete_test_work(work_id)
        delete_test_work(dead_letter_id)


if __name__ == "__main__":
    main()