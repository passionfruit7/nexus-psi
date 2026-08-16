from nexus.storage.database import connect
from nexus.operator.runtime import OperatorRuntime


def get_system_summary():
    """
    Return a high-level summary of the current NEXUS system.

    This is intended for the operator dashboard.
    """

    connection = connect()

    try:
        work_counts = connection.execute(
            """
            SELECT
                status,
                COUNT(*) AS count
            FROM work_items
            GROUP BY status
            ORDER BY status
            """
        ).fetchall()

        attempt_count = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM attempts
            """
        ).fetchone()["count"]

        event_count = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM events
            """
        ).fetchone()["count"]

        dedupe_count = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM dedupe_records
            """
        ).fetchone()["count"]

        counts = {
            row["status"]: row["count"]
            for row in work_counts
        }

        return {
            "work": {
                "total": sum(counts.values()),
                "queued": counts.get("QUEUED", 0),
                "running": counts.get("RUNNING", 0),
                "succeeded": counts.get("SUCCEEDED", 0),
                "dead_lettered": counts.get(
                    "DEAD_LETTERED",
                    0,
                ),
            },
            "attempts": attempt_count,
            "events": event_count,
            "dedupe_records": dedupe_count,
        }

    finally:
        connection.close()


def get_queue_summary():
    """
    Return counts for each important work state.
    """

    connection = connect()

    try:
        rows = connection.execute(
            """
            SELECT
                status,
                COUNT(*) AS count
            FROM work_items
            GROUP BY status
            ORDER BY status
            """
        ).fetchall()

        counts = {
            row["status"]: row["count"]
            for row in rows
        }

        return {
            "QUEUED": counts.get("QUEUED", 0),
            "RUNNING": counts.get("RUNNING", 0),
            "SUCCEEDED": counts.get(
                "SUCCEEDED",
                0,
            ),
            "DEAD_LETTERED": counts.get(
                "DEAD_LETTERED",
                0,
            ),
        }

    finally:
        connection.close()


def get_work_items(
    *,
    status=None,
    limit=100,
):
    """
    Return work items for the operator.

    If status is supplied, only work items in that state
    are returned.
    """

    if limit < 1:
        raise ValueError(
            "limit must be at least 1"
        )

    connection = connect()

    try:
        if status is None:
            rows = connection.execute(
                """
                SELECT
                    id,
                    type,
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
                FROM work_items
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        else:
            rows = connection.execute(
                """
                SELECT
                    id,
                    type,
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
                FROM work_items
                WHERE status = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (
                    status,
                    limit,
                ),
            ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


def get_work_item(work_id):
    """
    Return one work item by ID.

    Returns None when the work item does not exist.
    """

    if not work_id:
        raise ValueError(
            "work_id is required"
        )

    connection = connect()

    try:
        row = connection.execute(
            """
            SELECT
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
            FROM work_items
            WHERE id = ?
            """,
            (work_id,),
        ).fetchone()

        return dict(row) if row else None

    finally:
        connection.close()


def get_attempts(
    work_id,
):
    """
    Return the complete attempt history for a work item.
    """

    if not work_id:
        raise ValueError(
            "work_id is required"
        )

    connection = connect()

    try:
        rows = connection.execute(
            """
            SELECT
                id,
                work_id,
                attempt_number,
                worker_id,
                started_at,
                finished_at,
                outcome,
                error,
                release_id
            FROM attempts
            WHERE work_id = ?
            ORDER BY attempt_number ASC
            """,
            (work_id,),
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


def get_work_timeline(
    work_id,
):
    """
    Return the event timeline for a work item.

    This is the primary operator explanation view for
    understanding what happened to a piece of work.
    """

    if not work_id:
        raise ValueError(
            "work_id is required"
        )

    connection = connect()

    try:
        rows = connection.execute(
            """
            SELECT
                id,
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
            FROM events
            WHERE work_id = ?
            ORDER BY occurred_at ASC, id ASC
            """,
            (work_id,),
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


def get_recent_events(
    *,
    limit=50,
):
    """
    Return the most recent system events.
    """

    if limit < 1:
        raise ValueError(
            "limit must be at least 1"
        )

    connection = connect()

    try:
        rows = connection.execute(
            """
            SELECT
                id,
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
            FROM events
            ORDER BY occurred_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


def get_recent_failures(
    *,
    limit=50,
):
    """
    Return recent failure-related events.

    This includes worker crashes, failed attempts,
    dead-letter transitions, and other ERROR/WARNING
    events recorded by NEXUS.
    """

    if limit < 1:
        raise ValueError(
            "limit must be at least 1"
        )

    connection = connect()

    try:
        rows = connection.execute(
            """
            SELECT
                id,
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
            FROM events
            WHERE severity IN (
                'ERROR',
                'WARNING'
            )
            ORDER BY occurred_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


def get_dead_letter_items(
    *,
    limit=100,
):
    """
    Return work items that exhausted their retry budget.
    """

    return get_work_items(
        status="DEAD_LETTERED",
        limit=limit,
    )


def get_retrying_items(
    *,
    limit=100,
):
    """
    Return work items currently waiting for another attempt.

    A retrying item is QUEUED but has already consumed at
    least one attempt.
    """

    if limit < 1:
        raise ValueError(
            "limit must be at least 1"
        )

    connection = connect()

    try:
        rows = connection.execute(
            """
            SELECT
                id,
                type,
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
            FROM work_items
            WHERE status = 'QUEUED'
              AND attempt_count > 0
            ORDER BY next_attempt_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


def get_running_items(
    *,
    limit=100,
):
    """
    Return currently running work.
    """

    return get_work_items(
        status="RUNNING",
        limit=limit,
    )


def get_queued_items(
    *,
    limit=100,
):
    """
    Return currently queued work.
    """

    return get_work_items(
        status="QUEUED",
        limit=limit,
    )


def get_succeeded_items(
    *,
    limit=100,
):
    """
    Return recently succeeded work.
    """

    return get_work_items(
        status="SUCCEEDED",
        limit=limit,
    )


def get_worker_work(
    worker_id,
):
    """
    Return work currently assigned to a worker.
    """

    if not worker_id:
        raise ValueError(
            "worker_id is required"
        )

    connection = connect()

    try:
        rows = connection.execute(
            """
            SELECT
                id,
                type,
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
            FROM work_items
            WHERE worker_id = ?
            ORDER BY updated_at DESC
            """,
            (worker_id,),
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


def get_worker_summary():
    """
    Return a database-derived summary of workers.

    Worker liveness itself is maintained by Supervisor and
    will be added to the operator layer when we connect the
    live Supervisor state.

    For now this shows workers that have appeared in work
    or event history.
    """

    connection = connect()

    try:
        rows = connection.execute(
            """
            SELECT
                worker_id,
                COUNT(*) AS event_count,
                MAX(occurred_at) AS last_event_at
            FROM events
            WHERE worker_id IS NOT NULL
            GROUP BY worker_id
            ORDER BY last_event_at DESC
            """
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()

def get_live_worker_state(
    supervisor,
    worker_id,
):
    """
    Return live state for one worker.

    Live process state comes from Supervisor, not SQLite.
    """

    runtime = OperatorRuntime(supervisor)

    return runtime.get_worker_state(
        worker_id
    )


def get_live_workers(
    supervisor,
):
    """
    Return live state for all supervised workers.
    """

    runtime = OperatorRuntime(supervisor)

    return runtime.get_workers()


def get_runtime_summary(
    supervisor,
):
    """
    Return a live summary of the Supervisor runtime.
    """

    runtime = OperatorRuntime(supervisor)

    return runtime.get_runtime_summary()