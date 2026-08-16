import argparse
import json
import os
import time

from nexus.core.events import record_event
from nexus.storage.database import connect, initialize


# ============================================================
# WORKER CONFIGURATION
# ============================================================

POLL_INTERVAL_SECONDS = 0.2

PROCESSING_SECONDS = float(
    os.environ.get(
        "NEXUS_PROCESSING_SECONDS",
        "0.5",
    )
)

RETRY_BASE_DELAY_SECONDS = float(
    os.environ.get(
        "NEXUS_RETRY_BASE_DELAY_SECONDS",
        "1.0",
    )
)


# ============================================================
# WORK CLAIMING
# ============================================================

def claim_work(connection, worker_id):
    """
    Atomically claim the oldest available queued work item.

    SQLite's BEGIN IMMEDIATE ensures that two workers cannot
    successfully claim the same work item at the same time.

    State transition:

        QUEUED
           |
           v
        RUNNING
    """

    connection.execute("BEGIN IMMEDIATE")

    try:
        row = connection.execute(
            """
            SELECT
                *
            FROM work_items
            WHERE status = 'QUEUED'
              AND (
                    next_attempt_at IS NULL
                    OR next_attempt_at <= ?
              )
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (time.time(),),
        ).fetchone()

        if row is None:
            connection.execute("COMMIT")
            return None

        attempt_number = (
            row["attempt_count"] + 1
        )

        now = time.time()

        updated = connection.execute(
            """
            UPDATE work_items
            SET
                status = 'RUNNING',
                attempt_count = ?,
                worker_id = ?,
                updated_at = ?
            WHERE id = ?
              AND status = 'QUEUED'
            """,
            (
                attempt_number,
                worker_id,
                now,
                row["id"],
            ),
        )

        if updated.rowcount != 1:
            connection.execute("ROLLBACK")
            return None

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
                ?,
                ?,
                ?,
                NULL,
                NULL,
                NULL,
                ?
            )
            """,
            (
                row["id"],
                attempt_number,
                worker_id,
                now,
                row["release_id"],
            ),
        )

        record_event(
            connection,
            "WORK_STARTED",
            subject_type="work",
            subject_id=row["id"],
            work_id=row["id"],
            worker_id=worker_id,
            release_id=row["release_id"],
            severity="INFO",
            decision="CLAIM",
            reason="dispatcher_assignment",
            message=(
                f"Worker {worker_id} started "
                f"attempt {attempt_number}"
            ),
        )

        connection.execute("COMMIT")

        return {
            "id": row["id"],
            "type": row["type"],
            "body_json": row["body_json"],
            "attempt_number": attempt_number,
            "release_id": row["release_id"],
            "max_attempts": row["max_attempts"],
        }

    except Exception:
        connection.execute("ROLLBACK")
        raise


# ============================================================
# RETRY CALCULATION
# ============================================================

def calculate_retry_delay(attempt_number):
    """
    Calculate exponential retry delay.

    Attempt 1 failure:
        1 second

    Attempt 2 failure:
        2 seconds

    Attempt 3 failure:
        4 seconds

    The base delay can be changed using:

        NEXUS_RETRY_BASE_DELAY_SECONDS
    """

    return RETRY_BASE_DELAY_SECONDS * (
        2 ** max(attempt_number - 1, 0)
    )


# ============================================================
# DETERMINISTIC FAILURE INJECTION
# ============================================================

def should_fail(work_body, attempt_number):
    """
    Determine whether the current attempt should fail.

    Supported testing payload:

        {
            "fail_attempts": 2
        }

    This produces:

        attempt 1 -> FAILED
        attempt 2 -> FAILED
        attempt 3 -> SUCCESS

    Permanent failure:

        {
            "always_fail": true
        }

    This produces:

        attempt 1 -> FAILED
        attempt 2 -> FAILED
        ...
        max attempts -> DEAD_LETTERED
    """

    if work_body.get("always_fail") is True:
        return True

    fail_attempts = work_body.get(
        "fail_attempts",
        0,
    )

    try:
        fail_attempts = int(
            fail_attempts
        )
    except (
        TypeError,
        ValueError,
    ):
        fail_attempts = 0

    return attempt_number <= fail_attempts


def failure_is_retryable(work_body):
    """
    Determine whether a simulated/application failure
    should be retried.

    By default failures are retryable.

    A work item may explicitly specify:

        {
            "failure_retryable": false
        }

    which causes the failure to become terminal immediately.
    """

    return (
        work_body.get(
            "failure_retryable",
            True,
        )
        is True
    )


# ============================================================
# FAILURE HANDLING
# ============================================================

def handle_work_failure(
    connection,
    worker_id,
    work,
    error_message,
    retryable=True,
):
    """
    Handle one failed work attempt.

    Retryable failure with attempts remaining:

        RUNNING
            |
            v
        QUEUED
            |
            v
        retry

    Retryable failure with no attempts remaining:

        RUNNING
            |
            v
        DEAD_LETTERED

    Non-retryable failure:

        RUNNING
            |
            v
        DEAD_LETTERED
    """

    work_id = work["id"]

    attempt_number = (
        work["attempt_number"]
    )

    max_attempts = (
        work["max_attempts"]
    )

    now = time.time()

    connection.execute("BEGIN IMMEDIATE")

    try:
        # ----------------------------------------------------
        # Finish the current attempt
        # ----------------------------------------------------

        connection.execute(
            """
            UPDATE attempts
            SET
                finished_at = ?,
                outcome = 'FAILED',
                error = ?
            WHERE work_id = ?
              AND attempt_number = ?
              AND finished_at IS NULL
            """,
            (
                now,
                error_message,
                work_id,
                attempt_number,
            ),
        )

        attempts_remaining = (
            attempt_number < max_attempts
        )

        # ----------------------------------------------------
        # RETRY
        # ----------------------------------------------------

        if retryable and attempts_remaining:

            retry_delay = (
                calculate_retry_delay(
                    attempt_number
                )
            )

            next_attempt_at = (
                now + retry_delay
            )

            connection.execute(
                """
                UPDATE work_items
                SET
                    status = 'QUEUED',
                    worker_id = NULL,
                    updated_at = ?,
                    next_attempt_at = ?,
                    last_error = ?,
                    final_reason = NULL
                WHERE id = ?
                  AND status = 'RUNNING'
                """,
                (
                    now,
                    next_attempt_at,
                    error_message,
                    work_id,
                ),
            )

            record_event(
                connection,
                "WORK_FAILED_RETRYING",
                subject_type="work",
                subject_id=work_id,
                work_id=work_id,
                worker_id=worker_id,
                severity="WARNING",
                decision="RETRY",
                reason="retryable_failure",
                before={
                    "status": "RUNNING",
                    "attempt": attempt_number,
                },
                after={
                    "status": "QUEUED",
                    "next_attempt_at": (
                        next_attempt_at
                    ),
                },
                message=(
                    f"Work {work_id} failed "
                    f"attempt {attempt_number}; "
                    f"retry scheduled in "
                    f"{retry_delay:.2f}s"
                ),
            )

            connection.execute("COMMIT")

            print(
                f"[{worker_id}] {work_id} "
                f"failed; retry scheduled",
                flush=True,
            )

            return "RETRY"

        # ----------------------------------------------------
        # DEAD LETTER
        # ----------------------------------------------------

        if not retryable:
            final_reason = (
                "non_retryable_failure"
            )
        else:
            final_reason = (
                "max_attempts_exhausted"
            )

        connection.execute(
            """
            UPDATE work_items
            SET
                status = 'DEAD_LETTERED',
                worker_id = NULL,
                updated_at = ?,
                completed_at = ?,
                last_error = ?,
                final_reason = ?
            WHERE id = ?
              AND status = 'RUNNING'
            """,
            (
                now,
                now,
                error_message,
                final_reason,
                work_id,
            ),
        )

        connection.execute(
            """
            UPDATE dedupe_records
            SET
                status = 'DEAD_LETTERED'
            WHERE work_id = ?
            """,
            (work_id,),
        )

        record_event(
            connection,
            "WORK_DEAD_LETTERED",
            subject_type="work",
            subject_id=work_id,
            work_id=work_id,
            worker_id=worker_id,
            severity="ERROR",
            decision="DEAD_LETTER",
            reason=final_reason,
            before={
                "status": "RUNNING",
                "attempt": attempt_number,
            },
            after={
                "status": "DEAD_LETTERED",
            },
            message=(
                f"Work {work_id} moved to "
                "DEAD_LETTERED"
            ),
        )

        connection.execute("COMMIT")

        print(
            f"[{worker_id}] {work_id} "
            "moved to DEAD_LETTERED",
            flush=True,
        )

        return "DEAD_LETTERED"

    except Exception:
        connection.execute("ROLLBACK")
        raise


# ============================================================
# WORK SUCCESS
# ============================================================

def complete_work(
    connection,
    worker_id,
    work,
):
    """
    Mark a work item as successfully completed.

    State transition:

        RUNNING
           |
           v
        SUCCEEDED
    """

    work_id = work["id"]

    attempt_number = (
        work["attempt_number"]
    )

    now = time.time()

    connection.execute("BEGIN IMMEDIATE")

    try:
        updated = connection.execute(
            """
            UPDATE work_items
            SET
                status = 'SUCCEEDED',
                updated_at = ?,
                completed_at = ?,
                last_error = NULL,
                final_reason = ?
            WHERE id = ?
              AND status = 'RUNNING'
            """,
            (
                now,
                now,
                "processed_successfully",
                work_id,
            ),
        )

        if updated.rowcount != 1:
            connection.execute(
                "ROLLBACK"
            )
            return False

        connection.execute(
            """
            UPDATE attempts
            SET
                finished_at = ?,
                outcome = 'SUCCEEDED',
                error = NULL
            WHERE work_id = ?
              AND attempt_number = ?
              AND finished_at IS NULL
            """,
            (
                now,
                work_id,
                attempt_number,
            ),
        )

        connection.execute(
            """
            UPDATE dedupe_records
            SET
                status = 'COMPLETED',
                completed_at = ?
            WHERE work_id = ?
            """,
            (
                now,
                work_id,
            ),
        )

        record_event(
            connection,
            "WORK_SUCCEEDED",
            subject_type="work",
            subject_id=work_id,
            work_id=work_id,
            worker_id=worker_id,
            release_id=work["release_id"],
            severity="INFO",
            decision="COMPLETE",
            reason="processing_success",
            before={
                "status": "RUNNING",
                "attempt": attempt_number,
            },
            after={
                "status": "SUCCEEDED",
            },
            message=(
                f"Work {work_id} completed"
            ),
        )

        connection.execute("COMMIT")

        print(
            f"[{worker_id}] completed "
            f"{work_id}",
            flush=True,
        )

        return True

    except Exception:
        connection.execute("ROLLBACK")
        raise


# ============================================================
# WORK PROCESSING
# ============================================================

def process_work(
    connection,
    worker_id,
    work,
):
    """
    Execute one piece of work.

    This function deliberately has ONE failure path.

    Processing decision:

        should_fail()
             |
       +-----+-----+
       |           |
      YES          NO
       |           |
       v           v
    failure     process
    handler         |
       |            v
       |         SUCCESS
       |
       +--> RETRY / DEAD_LETTER
    """

    work_id = work["id"]

    attempt_number = (
        work["attempt_number"]
    )

    body = json.loads(
        work["body_json"]
    )

    print(
        f"[{worker_id}] processing "
        f"{work_id}: {body}",
        flush=True,
    )

    # --------------------------------------------------------
    # Deterministic failure injection
    # --------------------------------------------------------

    if should_fail(
        body,
        attempt_number,
    ):

        retryable = (
            failure_is_retryable(
                body
            )
        )

        error_message = (
            f"Simulated failure on "
            f"attempt {attempt_number}"
        )

        handle_work_failure(
            connection,
            worker_id,
            work,
            error_message,
            retryable=retryable,
        )

        return

    # --------------------------------------------------------
    # Simulated processing time
    # --------------------------------------------------------

    time.sleep(
        PROCESSING_SECONDS
    )

    # --------------------------------------------------------
    # Successful completion
    # --------------------------------------------------------

    complete_work(
        connection,
        worker_id,
        work,
    )


# ============================================================
# WORKER RUNTIME
# ============================================================

def run_worker(worker_id):
    """
    Run one worker continuously.

    The worker:

        1. initializes the database
        2. connects to SQLite
        3. records WORKER_STARTED
        4. claims work
        5. processes work
        6. repeats
        7. records WORKER_STOPPED on Ctrl+C
    """

    initialize()

    connection = connect()

    print(
        f"[{worker_id}] worker started",
        flush=True,
    )

    record_event(
        connection,
        "WORKER_STARTED",
        subject_type="worker",
        subject_id=worker_id,
        worker_id=worker_id,
        severity="INFO",
        decision="START",
        reason="worker_startup",
        message=(
            f"{worker_id} started"
        ),
    )

    try:
        while True:

            work = claim_work(
                connection,
                worker_id,
            )

            if work is None:
                time.sleep(
                    POLL_INTERVAL_SECONDS
                )
                continue

            process_work(
                connection,
                worker_id,
                work,
            )

    except KeyboardInterrupt:

        print(
            f"[{worker_id}] "
            "worker stopping",
            flush=True,
        )

        record_event(
            connection,
            "WORKER_STOPPED",
            subject_type="worker",
            subject_id=worker_id,
            worker_id=worker_id,
            severity="INFO",
            decision="STOP",
            reason="operator_interrupt",
            message=(
                f"{worker_id} stopped "
                "by operator"
            ),
        )

    finally:
        connection.close()


# ============================================================
# COMMAND-LINE ENTRY POINT
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="NEXUS worker process"
    )

    parser.add_argument(
        "--worker-id",
        required=True,
        help="Unique worker identifier",
    )

    args = parser.parse_args()

    run_worker(
        args.worker_id
    )


if __name__ == "__main__":
    main()