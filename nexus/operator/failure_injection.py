import json
import os
import signal
import time

from nexus.core.events import record_event
from nexus.operator.commands import OperatorCommandError
from nexus.storage.database import connect


FAILURE_TRANSIENT = "TRANSIENT_FAILURE"
FAILURE_PERMANENT = "PERMANENT_FAILURE"
FAILURE_KILL_WORKER = "KILL_WORKER"


def _get_work(connection, work_id):
    return connection.execute(
        """
        SELECT
            id,
            type,
            body_json,
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


def inject_transient_failure(
    work_id,
    fail_attempts=1,
):
    """
    Configure a work item to fail a specified number of
    attempts and then continue normally.

    Example:

        fail_attempts=2

        attempt 1 -> FAILED
        attempt 2 -> FAILED
        attempt 3 -> normal processing
    """

    if not work_id:
        raise OperatorCommandError(
            "work_id is required"
        )

    if fail_attempts < 1:
        raise OperatorCommandError(
            "fail_attempts must be at least 1"
        )

    connection = connect()

    try:
        connection.execute("BEGIN IMMEDIATE")

        work = _get_work(
            connection,
            work_id,
        )

        if work is None:
            connection.execute("ROLLBACK")

            raise OperatorCommandError(
                f"Unknown work item: {work_id}"
            )

        if work["status"] not in {
            "QUEUED",
            "RUNNING",
        }:
            connection.execute("ROLLBACK")

            raise OperatorCommandError(
                f"Cannot inject transient failure into "
                f"{work_id} from status "
                f"{work['status']}"
            )

        body = json.loads(
            work["body_json"]
        )

        body["__nexus_failure"] = {
            "type": FAILURE_TRANSIENT,
            "remaining_failures": fail_attempts,
        }

        now = time.time()

        connection.execute(
            """
            UPDATE work_items
            SET
                body_json = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                json.dumps(
                    body,
                    sort_keys=True,
                ),
                now,
                work_id,
            ),
        )

        record_event(
            connection,
            "FAILURE_INJECTED",
            subject_type="work",
            subject_id=work_id,
            work_id=work_id,
            severity="WARNING",
            decision="INJECT",
            reason="operator_failure_injection",
            after={
                "failure_type": FAILURE_TRANSIENT,
                "fail_attempts": fail_attempts,
            },
            message=(
                f"Injected transient failure into "
                f"work {work_id} for "
                f"{fail_attempts} attempt(s)"
            ),
        )

        connection.execute("COMMIT")

        return {
            "success": True,
            "failure_type": FAILURE_TRANSIENT,
            "work_id": work_id,
            "fail_attempts": fail_attempts,
        }

    except Exception:
        try:
            connection.execute("ROLLBACK")
        except Exception:
            pass

        raise

    finally:
        connection.close()


def inject_permanent_failure(
    work_id,
):
    """
    Configure a work item to fail on every attempt.

    The normal retry budget will eventually move the work
    item to DEAD_LETTERED.
    """

    if not work_id:
        raise OperatorCommandError(
            "work_id is required"
        )

    connection = connect()

    try:
        connection.execute("BEGIN IMMEDIATE")

        work = _get_work(
            connection,
            work_id,
        )

        if work is None:
            connection.execute("ROLLBACK")

            raise OperatorCommandError(
                f"Unknown work item: {work_id}"
            )

        if work["status"] not in {
            "QUEUED",
            "RUNNING",
        }:
            connection.execute("ROLLBACK")

            raise OperatorCommandError(
                f"Cannot inject permanent failure into "
                f"{work_id} from status "
                f"{work['status']}"
            )

        body = json.loads(
            work["body_json"]
        )

        body["__nexus_failure"] = {
            "type": FAILURE_PERMANENT,
        }

        now = time.time()

        connection.execute(
            """
            UPDATE work_items
            SET
                body_json = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                json.dumps(
                    body,
                    sort_keys=True,
                ),
                now,
                work_id,
            ),
        )

        record_event(
            connection,
            "FAILURE_INJECTED",
            subject_type="work",
            subject_id=work_id,
            work_id=work_id,
            severity="WARNING",
            decision="INJECT",
            reason="operator_failure_injection",
            after={
                "failure_type": FAILURE_PERMANENT,
            },
            message=(
                f"Injected permanent failure into "
                f"work {work_id}"
            ),
        )

        connection.execute("COMMIT")

        return {
            "success": True,
            "failure_type": FAILURE_PERMANENT,
            "work_id": work_id,
        }

    except Exception:
        try:
            connection.execute("ROLLBACK")
        except Exception:
            pass

        raise

    finally:
        connection.close()


def kill_worker(
    supervisor,
    worker_id,
):
    """
    Deliberately kill a worker process.

    SIGKILL is used so that this represents a genuine
    unexpected process death. The Supervisor must recover
    any RUNNING work owned by the worker.
    """

    if not worker_id:
        raise OperatorCommandError(
            "worker_id is required"
        )

    if worker_id not in supervisor.workers:
        raise OperatorCommandError(
            f"Unknown worker: {worker_id}"
        )

    worker = supervisor.workers[worker_id]

    if worker.process is None:
        raise OperatorCommandError(
            f"Worker {worker_id} is not running"
        )

    process = worker.process

    if process.poll() is not None:
        raise OperatorCommandError(
            f"Worker {worker_id} has already exited"
        )

    pid = process.pid

    connection = connect()

    try:
        record_event(
            connection,
            "FAILURE_INJECTED",
            subject_type="worker",
            subject_id=worker_id,
            worker_id=worker_id,
            severity="ERROR",
            decision="INJECT",
            reason="operator_kill_worker",
            before={
                "state": worker.state,
                "pid": pid,
            },
            after={
                "expected": "PROCESS_EXIT",
            },
            message=(
                f"Operator deliberately killed "
                f"worker {worker_id} "
                f"(pid={pid})"
            ),
        )

    finally:
        connection.close()

    os.kill(
        pid,
        signal.SIGKILL,
    )

    return {
        "success": True,
        "failure_type": FAILURE_KILL_WORKER,
        "worker_id": worker_id,
        "pid": pid,
    }