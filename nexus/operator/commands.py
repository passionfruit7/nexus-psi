import time

from nexus.core.events import record_event
from nexus.operator.runtime import OperatorRuntime
from nexus.storage.database import connect


class OperatorCommandError(Exception):
    """
    Raised when an operator command cannot be safely executed.
    """


def _get_work(connection, work_id):
    return connection.execute(
        """
        SELECT
            id,
            type,
            status,
            attempt_count,
            max_attempts,
            worker_id,
            release_id,
            next_attempt_at,
            last_error,
            final_reason
        FROM work_items
        WHERE id = ?
        """,
        (work_id,),
    ).fetchone()


def start_worker(
    supervisor,
    worker_id,
):
    """
    Start one worker through the Supervisor.
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

    if worker.process is not None:
        if worker.process.poll() is None:
            raise OperatorCommandError(
                f"Worker {worker_id} is already running"
            )

    supervisor.start_worker(worker_id)

    connection = connect()

    try:
        record_event(
            connection,
            "OPERATOR_WORKER_STARTED",
            subject_type="worker",
            subject_id=worker_id,
            worker_id=worker_id,
            severity="INFO",
            decision="START",
            reason="operator_command",
            message=(
                f"Operator started worker {worker_id}"
            ),
        )

    finally:
        connection.close()

    return {
        "success": True,
        "command": "start_worker",
        "worker_id": worker_id,
        "state": "RUNNING",
        "pid": worker.process.pid
        if worker.process is not None
        else None,
    }


def stop_worker(
    supervisor,
    worker_id,
):
    """
    Stop one worker through the Supervisor.
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

    supervisor.stop_worker(worker_id)

    connection = connect()

    try:
        record_event(
            connection,
            "OPERATOR_WORKER_STOPPED",
            subject_type="worker",
            subject_id=worker_id,
            worker_id=worker_id,
            severity="WARNING",
            decision="STOP",
            reason="operator_command",
            message=(
                f"Operator stopped worker {worker_id}"
            ),
        )

    finally:
        connection.close()

    return {
        "success": True,
        "command": "stop_worker",
        "worker_id": worker_id,
        "state": "STOPPED",
    }


def restart_worker(
    supervisor,
    worker_id,
):
    """
    Restart one worker.

    The old process is stopped first, then a new process
    is started.
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

    if worker.process is not None:
        if worker.process.poll() is None:
            supervisor.stop_worker(worker_id)

    supervisor.start_worker(worker_id)

    connection = connect()

    try:
        record_event(
            connection,
            "OPERATOR_WORKER_RESTARTED",
            subject_type="worker",
            subject_id=worker_id,
            worker_id=worker_id,
            severity="WARNING",
            decision="RESTART",
            reason="operator_command",
            message=(
                f"Operator restarted worker {worker_id}"
            ),
        )

    finally:
        connection.close()

    worker = supervisor.workers[worker_id]

    return {
        "success": True,
        "command": "restart_worker",
        "worker_id": worker_id,
        "state": worker.state,
        "pid": (
            worker.process.pid
            if worker.process is not None
            else None
        ),
    }


def requeue_work(
    work_id,
):
    """
    Safely return a failed/dead-lettered work item to QUEUED.

    This command intentionally does NOT permit arbitrary
    state changes such as SUCCEEDED -> RUNNING.
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

        current_status = work["status"]

        allowed_statuses = {
            "DEAD_LETTERED",
        }

        if current_status not in allowed_statuses:
            connection.execute("ROLLBACK")

            raise OperatorCommandError(
                f"Cannot requeue work {work_id} "
                f"from status {current_status}"
            )

        now = time.time()

        connection.execute(
            """
            UPDATE work_items
            SET
                status = 'QUEUED',
                updated_at = ?,
                next_attempt_at = ?,
                worker_id = NULL,
                final_reason = NULL
            WHERE id = ?
              AND status = 'DEAD_LETTERED'
            """,
            (
                now,
                now,
                work_id,
            ),
        )

        record_event(
            connection,
            "OPERATOR_WORK_REQUEUED",
            subject_type="work",
            subject_id=work_id,
            work_id=work_id,
            severity="WARNING",
            decision="REQUEUE",
            reason="operator_command",
            before={
                "status": current_status,
                "attempt_count": work[
                    "attempt_count"
                ],
            },
            after={
                "status": "QUEUED",
                "attempt_count": work[
                    "attempt_count"
                ],
            },
            message=(
                f"Operator requeued work {work_id}"
            ),
        )

        connection.execute("COMMIT")

        return {
            "success": True,
            "command": "requeue_work",
            "work_id": work_id,
            "previous_status": current_status,
            "status": "QUEUED",
        }

    except Exception:
        try:
            connection.execute("ROLLBACK")
        except Exception:
            pass

        raise

    finally:
        connection.close()


def retry_dead_letter(
    work_id,
):
    """
    Explicit operator action to retry a dead-lettered item.

    This is currently an alias with a more explicit command
    name for the operator UI.
    """

    result = requeue_work(work_id)

    result["command"] = "retry_dead_letter"

    return result