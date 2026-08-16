import os
import signal
import time
import uuid

from nexus.core.intake import accept_work
from nexus.core.supervisor import Supervisor
from nexus.storage.database import connect, initialize


WORKER_ID = "worker-recovery-test"


def get_work(work_id):
    """
    Return the current state of a work item.
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
                worker_id,
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
    """
    Return all attempts for a work item.
    """

    connection = connect()

    try:
        rows = connection.execute(
            """
            SELECT
                attempt_number,
                worker_id,
                started_at,
                finished_at,
                outcome,
                error
            FROM attempts
            WHERE work_id = ?
            ORDER BY attempt_number ASC
            """,
            (work_id,),
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


def get_events(work_id):
    """
    Return all events for a work item.
    """

    connection = connect()

    try:
        rows = connection.execute(
            """
            SELECT
                event_type,
                worker_id,
                decision,
                reason,
                message
            FROM events
            WHERE work_id = ?
            ORDER BY id ASC
            """,
            (work_id,),
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


def wait_for_status(
    work_id,
    expected_status,
    timeout=10,
):
    """
    Wait until a work item reaches the expected status.
    """

    deadline = time.time() + timeout

    while time.time() < deadline:
        state = get_work(work_id)

        if (
            state is not None
            and state["status"] == expected_status
        ):
            return state

        time.sleep(0.1)

    state = get_work(work_id)

    raise AssertionError(
        f"Work {work_id} did not reach "
        f"{expected_status} within {timeout}s. "
        f"Final observed state: {state}"
    )


def wait_for_worker_recovery(
    supervisor,
    worker_id,
    timeout=10,
):
    """
    Allow the supervisor to detect a worker crash.

    Supervisor.check_workers() is the mechanism that detects
    process death, performs recovery of RUNNING work, and
    restarts the worker.
    """

    deadline = time.time() + timeout

    while time.time() < deadline:
        supervisor.check_workers()

        worker = supervisor.workers[worker_id]

        if worker.restart_count >= 1:
            return worker

        time.sleep(0.05)

    worker = supervisor.workers[worker_id]

    raise AssertionError(
        f"Supervisor did not detect/restart "
        f"{worker_id} within {timeout}s. "
        f"state={worker.state}, "
        f"restart_count={worker.restart_count}"
    )


def wait_for_recovered_work(
    work_id,
    timeout=10,
):
    """
    Wait until the crashed work item has been returned
    to the QUEUED state.
    """

    deadline = time.time() + timeout

    while time.time() < deadline:
        state = get_work(work_id)

        if (
            state is not None
            and state["status"] == "QUEUED"
            and state["worker_id"] is None
        ):
            return state

        time.sleep(0.05)

    state = get_work(work_id)

    raise AssertionError(
        f"Work {work_id} was not recovered within "
        f"{timeout}s. "
        f"Final observed state: {state}"
    )


def delete_test_work(work_id):
    """
    Remove a test-created work item and all dependent
    records.

    This is test cleanup only.
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
    print("=== NEXUS CRASH RECOVERY TEST ===")

    initialize()

    work_id = (
        "automated-recovery-"
        + uuid.uuid4().hex[:8]
    )

    supervisor = Supervisor(
        [WORKER_ID],
        max_restarts=5,
        restart_window_seconds=60,
        base_backoff_seconds=0.1,
        max_backoff_seconds=1,
    )

    try:
        # =================================================
        # 1. ACCEPT WORK
        # =================================================

        connection = connect()

        try:
            result = accept_work(
                connection,
                work_id,
                "demo",
                {
                    "message": (
                        "Automated crash recovery test"
                    ),
                },
            )

        finally:
            connection.close()

        print("Accepted:", result)

        assert result["accepted"] is True
        assert result["duplicate"] is False
        assert result["id"] == work_id
        assert result["status"] == "QUEUED"

        # =================================================
        # 2. START SUPERVISOR AND WORKER
        # =================================================

        supervisor.running = True
        supervisor.start_all()

        worker = supervisor.workers[WORKER_ID]

        assert worker.process is not None

        print(
            f"Worker started: {worker.process.pid}"
        )

        # =================================================
        # 3. WAIT UNTIL OUR WORK IS RUNNING
        # =================================================

        running = wait_for_status(
            work_id,
            "RUNNING",
            timeout=10,
        )

        print(
            "Job entered RUNNING:",
            running,
        )

        assert running["attempt_count"] == 1
        assert (
            running["worker_id"]
            == WORKER_ID
        )

        # =================================================
        # 4. KILL THE WORKER WHILE WORK IS RUNNING
        # =================================================

        worker = supervisor.workers[WORKER_ID]

        assert worker.process is not None

        worker_pid = worker.process.pid

        print(
            f"Killing worker {worker_pid} "
            f"while work is RUNNING"
        )

        os.kill(
            worker_pid,
            signal.SIGKILL,
        )

        # =================================================
        # 5. LET SUPERVISOR DETECT THE CRASH
        # =================================================

        restarted_worker = wait_for_worker_recovery(
            supervisor,
            WORKER_ID,
            timeout=10,
        )

        print(
            "Supervisor detected worker death."
        )

        # =================================================
        # 6. VERIFY WORK WAS RECOVERED
        # =================================================

        recovered = wait_for_recovered_work(
            work_id,
            timeout=10,
        )

        print(
            "State after crash recovery:",
            recovered,
        )

        assert recovered["status"] == "QUEUED"

        assert recovered["worker_id"] is None

        assert recovered["attempt_count"] == 1

        assert (
            recovered["last_error"]
            == f"worker_crashed:{WORKER_ID}"
        )

        assert recovered["final_reason"] is None

        # =================================================
        # 7. VERIFY WORKER WAS RESTARTED
        # =================================================

        assert (
            restarted_worker.restart_count
            >= 1
        )

        assert (
            restarted_worker.process
            is not None
        )

        print(
            "Worker restarted:",
            restarted_worker.process.pid,
        )

        # =================================================
        # 8. WAIT FOR RECOVERED WORK TO COMPLETE
        # =================================================

        completed = wait_for_status(
            work_id,
            "SUCCEEDED",
            timeout=15,
        )

        print(
            "Recovered job completed:",
            completed,
        )

        assert completed["status"] == "SUCCEEDED"

        assert completed["attempt_count"] == 2

        assert (
            completed["final_reason"]
            == "processed_successfully"
        )

        assert completed["last_error"] is None

        # =================================================
        # 9. VERIFY ATTEMPT HISTORY
        # =================================================

        attempts = get_attempts(work_id)

        print("Attempts:")

        for attempt in attempts:
            print(attempt)

        assert len(attempts) == 2

        first_attempt = attempts[0]
        second_attempt = attempts[1]

        assert (
            first_attempt["attempt_number"]
            == 1
        )

        assert (
            first_attempt["worker_id"]
            == WORKER_ID
        )

        assert (
            first_attempt["outcome"]
            == "WORKER_CRASHED"
        )

        assert (
            first_attempt["error"]
            == (
                f"Worker {WORKER_ID} "
                "exited before completing work"
            )
        )

        assert (
            first_attempt["finished_at"]
            is not None
        )

        assert (
            second_attempt["attempt_number"]
            == 2
        )

        assert (
            second_attempt["worker_id"]
            == WORKER_ID
        )

        assert (
            second_attempt["outcome"]
            == "SUCCEEDED"
        )

        assert second_attempt["error"] is None

        # =================================================
        # 10. VERIFY EVENT HISTORY
        # =================================================

        events = get_events(work_id)

        print("Events:")

        for event in events:
            print(event)

        event_types = [
            event["event_type"]
            for event in events
        ]

        assert "WORK_ACCEPTED" in event_types
        assert "WORK_STARTED" in event_types
        assert "WORK_RECOVERED" in event_types
        assert "WORK_SUCCEEDED" in event_types

        recovered_events = [
            event
            for event in events
            if event["event_type"]
            == "WORK_RECOVERED"
        ]

        assert len(recovered_events) == 1

        recovered_event = recovered_events[0]

        assert (
            recovered_event["worker_id"]
            == WORKER_ID
        )

        assert (
            recovered_event["decision"]
            == "REQUEUE"
        )

        assert (
            recovered_event["reason"]
            == "worker_crashed"
        )

        # =================================================
        # SUCCESS
        # =================================================

        print()
        print("===================================")
        print("CRASH RECOVERY TEST PASSED")
        print("===================================")

    finally:
        # =================================================
        # STOP SUPERVISOR / WORKER
        # =================================================

        supervisor.running = False

        worker = supervisor.workers[WORKER_ID]

        if worker.process is not None:
            supervisor.stop_worker(
                WORKER_ID
            )

        # =================================================
        # CLEAN TEST DATA
        # =================================================

        delete_test_work(work_id)


if __name__ == "__main__":
    main()