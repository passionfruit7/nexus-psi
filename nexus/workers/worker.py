import argparse
import json
import os
import time

from nexus.core.events import record_event
from nexus.storage.database import connect, initialize


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
        "1",
    )
)


def claim_work(connection, worker_id, work_id=None):
    """
    Atomically claim the oldest available queued work item.

    Only one worker can successfully claim a particular
    work item.
    """

    connection.execute("BEGIN IMMEDIATE")

    try:
        if work_id is None:
            row = connection.execute(
                """
                SELECT *
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

        else:
            row = connection.execute(
                """
                SELECT *
                FROM work_items
                WHERE id = ?
                AND status = 'QUEUED'
                AND (
                        next_attempt_at IS NULL
                        OR next_attempt_at <= ?
                )
                """,
                (
                    work_id,
                    time.time(),
                ),
            ).fetchone()

        if row is None:
            connection.execute("COMMIT")
            return None

        attempt_number = row["attempt_count"] + 1
        now = time.time()

        connection.execute(
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


def calculate_retry_delay(attempt_number):
    """
    Calculate exponential retry delay.

    Attempt 1 failure:
        base delay

    Attempt 2 failure:
        2 * base delay

    Attempt 3 failure:
        4 * base delay
    """

    return RETRY_BASE_DELAY_SECONDS * (
        2 ** max(attempt_number - 1, 0)
    )


def should_fail(work_body, attempt_number):
    """
    Deterministic failure injection for NEXUS testing.

    Supported payloads:

    {
        "fail_attempts": 2
    }

    Fails attempts 1 and 2, then succeeds.

    Or:

    {
        "always_fail": true
    }

    Fails every attempt.

    Optional:

    {
        "failure_retryable": false
    }

    Makes the injected failure terminal immediately.
    """

    if work_body.get("always_fail") is True:
        return True

    fail_attempts = work_body.get(
        "fail_attempts",
        0,
    )

    try:
        fail_attempts = int(fail_attempts)
    except (TypeError, ValueError):
        fail_attempts = 0

    return attempt_number <= fail_attempts


def failure_is_retryable(work_body):
    """
    Determine whether an application failure may be retried.

    By default simulated failures are retryable.
    """

    return work_body.get(
        "failure_retryable",
        True,
    ) is True


def handle_work_failure(
    connection,
    worker_id,
    work,
    error_message,
    retryable=True,
):
    """
    Handle a failed work attempt.

    If retryable and attempts remain:
        RUNNING -> QUEUED

    If retryable but no attempts remain:
        RUNNING -> DEAD_LETTERED

    If not retryable:
        RUNNING -> DEAD_LETTERED
    """

    work_id = work["id"]
    attempt_number = work["attempt_number"]
    max_attempts = work["max_attempts"]

    now = time.time()

    connection.execute("BEGIN IMMEDIATE")

    try:
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

        if retryable and attempts_remaining:
            retry_delay = calculate_retry_delay(
                attempt_number
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
                    "next_attempt_at": next_attempt_at,
                },
                message=(
                    f"Work {work_id} failed attempt "
                    f"{attempt_number}; retry scheduled "
                    f"in {retry_delay:.2f}s"
                ),
            )

            connection.execute("COMMIT")

            print(
                f"[{worker_id}] {work_id} failed; "
                f"retry scheduled",
                flush=True,
            )

            return "RETRY"

        # Terminal failure.
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
                (
                    "non_retryable_failure"
                    if not retryable
                    else "max_attempts_exhausted"
                ),
                work_id,
            ),
        )

        connection.execute(
            """
            UPDATE dedupe_records
            SET
                status = 'DEAD_LETTERED',
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
            "WORK_DEAD_LETTERED",
            subject_type="work",
            subject_id=work_id,
            work_id=work_id,
            worker_id=worker_id,
            severity="ERROR",
            decision="STOP_RETRYING",
            reason=(
                "non_retryable_failure"
                if not retryable
                else "max_attempts_exhausted"
            ),
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

def _handle_injected_failure(
    connection,
    worker_id,
    work,
    error_message,
):
    """
    Apply a deliberately injected application failure
    using the same retry/dead-letter path as a normal
    processing failure.
    """

    work_id = work["id"]
    attempt_number = work["attempt_number"]

    now = time.time()

    connection.execute("BEGIN IMMEDIATE")

    try:
        row = connection.execute(
            """
            SELECT
                attempt_count,
                max_attempts
            FROM work_items
            WHERE id = ?
            """,
            (work_id,),
        ).fetchone()

        attempt_count = row["attempt_count"]
        max_attempts = row["max_attempts"]

        connection.execute(
            """
            UPDATE attempts
            SET
                finished_at = ?,
                outcome = 'FAILED',
                error = ?
            WHERE work_id = ?
              AND attempt_number = ?
            """,
            (
                now,
                error_message,
                work_id,
                attempt_number,
            ),
        )

        if attempt_count >= max_attempts:
            connection.execute(
                """
                UPDATE work_items
                SET
                    status = 'DEAD_LETTERED',
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
                    "max_attempts_exhausted",
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
                reason="max_attempts_exhausted",
                message=(
                    f"Work {work_id} moved to "
                    "DEAD_LETTERED after injected "
                    "failure"
                ),
            )

            connection.execute("COMMIT")

            print(
                f"[{worker_id}] {work_id} "
                "moved to DEAD_LETTERED",
                flush=True,
            )

            return

        delay = min(
            2 ** attempt_number,
            16,
        )

        next_attempt_at = (
            now + delay
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
            "WORK_FAILED",
            subject_type="work",
            subject_id=work_id,
            work_id=work_id,
            worker_id=worker_id,
            severity="WARNING",
            decision="RETRY",
            reason="injected_failure",
            message=(
                f"Work {work_id} failed; "
                "retry scheduled"
            ),
        )

        connection.execute("COMMIT")

        print(
            f"[{worker_id}] {work_id} "
            "failed; retry scheduled",
            flush=True,
        )

    except Exception:
        connection.execute("ROLLBACK")
        raise
    
def process_work(connection, worker_id, work):
    """
    Execute one piece of work.

    Supports deterministic failure injection for
    retry and dead-letter testing.
    """

    work_id = work["id"]
    attempt_number = work["attempt_number"]

    body = json.loads(work["body_json"])

    print(
        f"[{worker_id}] processing {work_id}: {body}",
        flush=True,
    )

    failure_config = body.get(
        "__nexus_failure"
    )

    if failure_config is not None:
        failure_type = failure_config.get(
            "type"
        )

        if failure_type == "PERMANENT_FAILURE":
            _handle_injected_failure(
                connection,
                worker_id,
                work,
                "Injected permanent failure",
            )
            return

        if failure_type == "TRANSIENT_FAILURE":
            remaining = int(
                failure_config.get(
                    "remaining_failures",
                    0,
                )
            )

            if remaining > 0:
                failure_config[
                    "remaining_failures"
                ] = remaining - 1

                body["__nexus_failure"] = (
                    failure_config
                )

                connection.execute(
                    """
                    UPDATE work_items
                    SET
                        body_json = ?,
                        updated_at = ?
                    WHERE id = ?
                    AND status = 'RUNNING'
                    """,
                    (
                        json.dumps(
                            body,
                            sort_keys=True,
                        ),
                        time.time(),
                        work_id,
                    ),
                )

                _handle_injected_failure(
                    connection,
                    worker_id,
                    work,
                    (
                        "Injected transient failure "
                        f"(remaining={remaining - 1})"
                    ),
                )
                return

    time.sleep(PROCESSING_SECONDS)

    if should_fail(
        body,
        attempt_number,
    ):
        error_message = (
            f"Simulated failure on attempt "
            f"{attempt_number}"
        )

        retryable = failure_is_retryable(
            body
        )

        handle_work_failure(
            connection,
            worker_id,
            work,
            error_message,
            retryable=retryable,
        )

        return

    now = time.time()

    connection.execute("BEGIN IMMEDIATE")

    try:
        connection.execute(
            """
            UPDATE work_items
            SET
                status = 'SUCCEEDED',
                updated_at = ?,
                completed_at = ?,
                worker_id = ?,
                last_error = NULL,
                final_reason = ?
            WHERE id = ?
              AND status = 'RUNNING'
            """,
            (
                now,
                now,
                worker_id,
                "processed_successfully",
                work_id,
            ),
        )

        connection.execute(
            """
            UPDATE attempts
            SET
                finished_at = ?,
                outcome = 'SUCCEEDED'
            WHERE work_id = ?
              AND attempt_number = ?
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
            severity="INFO",
            decision="COMPLETE",
            reason="processing_success",
            message=f"Work {work_id} completed",
        )

        connection.execute("COMMIT")

        print(
            f"[{worker_id}] completed {work_id}",
            flush=True,
        )

    except Exception:
        connection.execute("ROLLBACK")
        raise


def run_worker(worker_id):
    """
    Run a worker continuously.
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
        reason="worker_launch",
        message=f"{worker_id} started",
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
            f"[{worker_id}] worker stopping",
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
                f"{worker_id} stopped by operator"
            ),
        )

    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--worker-id",
        required=True,
    )

    args = parser.parse_args()

    run_worker(args.worker_id)


if __name__ == "__main__":
    main()