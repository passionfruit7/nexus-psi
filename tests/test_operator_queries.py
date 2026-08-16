import uuid

from nexus.core.intake import accept_work
from nexus.operator.queries import (
    get_attempts,
    get_dead_letter_items,
    get_queue_summary,
    get_queued_items,
    get_recent_events,
    get_recent_failures,
    get_retrying_items,
    get_running_items,
    get_succeeded_items,
    get_system_summary,
    get_work_item,
    get_work_items,
    get_work_timeline,
    get_worker_summary,
    get_worker_work,
)
from nexus.storage.database import connect, initialize
from nexus.workers.worker import claim_work, process_work


def delete_test_work(work_id):
    """
    Remove a test-created work item and dependent records.
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


def main():
    print("=== NEXUS OPERATOR QUERY TEST ===")

    initialize()

    work_id = (
        "operator-query-"
        + uuid.uuid4().hex[:8]
    )

    try:
        # ---------------------------------------------
        # Create deterministic test work
        # ---------------------------------------------

        connection = connect()

        try:
            accepted = accept_work(
                connection,
                work_id,
                "operator-demo",
                {
                    "message": (
                        "Operator query test"
                    ),
                },
            )

        finally:
            connection.close()

        print("Accepted:")
        print(accepted)

        assert accepted["accepted"] is True
        assert accepted["duplicate"] is False

        # ---------------------------------------------
        # System summary
        # ---------------------------------------------

        summary = get_system_summary()

        print()
        print("System summary:")
        print(summary)

        assert "work" in summary
        assert "attempts" in summary
        assert "events" in summary
        assert "dedupe_records" in summary

        assert (
            summary["work"]["total"]
            >= 1
        )

        # ---------------------------------------------
        # Queue summary
        # ---------------------------------------------

        queue = get_queue_summary()

        print()
        print("Queue summary:")
        print(queue)

        assert "QUEUED" in queue
        assert "RUNNING" in queue
        assert "SUCCEEDED" in queue
        assert "DEAD_LETTERED" in queue

        assert queue["QUEUED"] >= 1

        # ---------------------------------------------
        # Specific work item
        # ---------------------------------------------

        item = get_work_item(work_id)

        print()
        print("Work item:")
        print(item)

        assert item is not None
        assert item["id"] == work_id
        assert item["status"] == "QUEUED"
        assert item["type"] == "operator-demo"
        assert item["attempt_count"] == 0

        # ---------------------------------------------
        # Queued items
        # ---------------------------------------------

        queued = get_queued_items(
            limit=100,
        )

        assert any(
            row["id"] == work_id
            for row in queued
        )

        # ---------------------------------------------
        # Generic work query
        # ---------------------------------------------

        all_items = get_work_items(
            limit=100,
        )

        assert any(
            row["id"] == work_id
            for row in all_items
        )

        # ---------------------------------------------
        # Claim work
        # ---------------------------------------------

        connection = connect()

        try:
            work = claim_work(
                connection,
                "operator-test-worker",
                work_id=work_id,
            )

        finally:
            connection.close()

        assert work is not None
        assert work["id"] == work_id

        running = get_work_item(work_id)

        print()
        print("Running work:")
        print(running)

        assert running["status"] == "RUNNING"
        assert running["attempt_count"] == 1

        # ---------------------------------------------
        # Running query
        # ---------------------------------------------

        running_items = get_running_items(
            limit=100,
        )

        assert any(
            row["id"] == work_id
            for row in running_items
        )

        # ---------------------------------------------
        # Worker work query
        # ---------------------------------------------

        worker_items = get_worker_work(
            "operator-test-worker",
        )

        assert any(
            row["id"] == work_id
            for row in worker_items
        )

        # ---------------------------------------------
        # Process work
        # ---------------------------------------------

        connection = connect()

        try:
            process_work(
                connection,
                "operator-test-worker",
                work,
            )

        finally:
            connection.close()

        completed = get_work_item(work_id)

        print()
        print("Completed work:")
        print(completed)

        assert completed["status"] == "SUCCEEDED"
        assert completed["attempt_count"] == 1

        # ---------------------------------------------
        # Succeeded query
        # ---------------------------------------------

        succeeded = get_succeeded_items(
            limit=100,
        )

        assert any(
            row["id"] == work_id
            for row in succeeded
        )

        # ---------------------------------------------
        # Attempt history
        # ---------------------------------------------

        attempts = get_attempts(work_id)

        print()
        print("Attempts:")
        print(attempts)

        assert len(attempts) == 1
        assert (
            attempts[0]["attempt_number"]
            == 1
        )
        assert (
            attempts[0]["outcome"]
            == "SUCCEEDED"
        )

        # ---------------------------------------------
        # Event timeline
        # ---------------------------------------------

        timeline = get_work_timeline(
            work_id,
        )

        print()
        print("Timeline:")

        for event in timeline:
            print(event)

        event_types = [
            event["event_type"]
            for event in timeline
        ]

        assert "WORK_ACCEPTED" in event_types
        assert "WORK_STARTED" in event_types
        assert "WORK_SUCCEEDED" in event_types

        # ---------------------------------------------
        # Recent events
        # ---------------------------------------------

        recent_events = get_recent_events(
            limit=100,
        )

        assert any(
            event["work_id"] == work_id
            for event in recent_events
        )

        # ---------------------------------------------
        # Recent failures
        # ---------------------------------------------

        failures = get_recent_failures(
            limit=100,
        )

        # There does not have to be a failure for this
        # successful test item. We only verify that the
        # function returns a list.
        assert isinstance(
            failures,
            list,
        )

        # ---------------------------------------------
        # Retry query
        # ---------------------------------------------

        retrying = get_retrying_items(
            limit=100,
        )

        assert isinstance(
            retrying,
            list,
        )

        # ---------------------------------------------
        # Dead-letter query
        # ---------------------------------------------

        dead_lettered = get_dead_letter_items(
            limit=100,
        )

        assert isinstance(
            dead_lettered,
            list,
        )

        # ---------------------------------------------
        # Worker summary
        # ---------------------------------------------

        workers = get_worker_summary()

        print()
        print("Worker summary:")
        print(workers)

        assert any(
            worker["worker_id"]
            == "operator-test-worker"
            for worker in workers
        )

        print()
        print("===================================")
        print("OPERATOR QUERY TEST PASSED")
        print("===================================")

    finally:
        delete_test_work(work_id)


if __name__ == "__main__":
    main()