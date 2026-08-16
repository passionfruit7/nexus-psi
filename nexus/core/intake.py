import json
import time

from nexus.core.events import record_event
from nexus.core.release_manager import get_active_release


DEFAULT_MAX_ATTEMPTS = 5


def accept_work(
    connection,
    work_id,
    work_type,
    body,
    max_attempts=DEFAULT_MAX_ATTEMPTS,
):
    """
    Durably accept one piece of work.

    The work item is associated with the currently active release
    at acceptance time.

    NEXUS only reports accepted=True after the work item,
    dedupe record, and acceptance event have been committed.
    """

    if not work_id:
        raise ValueError("work_id is required")

    if not work_type:
        raise ValueError("work_type is required")

    if not isinstance(body, dict):
        raise ValueError("body must be a dictionary")

    if max_attempts < 1:
        raise ValueError(
            "max_attempts must be at least 1"
        )

    now = time.time()

    # Determine which release is active before accepting work.
    active_release = get_active_release()

    release_id = (
        active_release["release_id"]
        if active_release is not None
        else None
    )

    connection.execute("BEGIN IMMEDIATE")

    try:
        existing = connection.execute(
            """
            SELECT id, status
            FROM work_items
            WHERE id = ?
            """,
            (work_id,),
        ).fetchone()

        if existing is not None:
            connection.execute("ROLLBACK")

            return {
                "accepted": True,
                "duplicate": True,
                "id": work_id,
                "status": existing["status"],
            }

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
                ?,
                ?,
                'QUEUED',
                0,
                ?,
                ?,
                ?,
                ?,
                NULL,
                ?,
                ?,
                NULL,
                NULL,
                NULL
            )
            """,
            (
                work_id,
                work_type,
                json.dumps(
                    body,
                    sort_keys=True,
                ),
                max_attempts,
                now,
                now,
                now,
                release_id,
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

        record_event(
            connection,
            "WORK_ACCEPTED",
            subject_type="work",
            subject_id=work_id,
            work_id=work_id,
            release_id=release_id,
            severity="INFO",
            decision="ACCEPT",
            reason="durable_write",
            after={
                "status": "QUEUED",
                "release_id": release_id,
            },
            message=(
                f"Work {work_id} accepted"
                + (
                    f" under release {release_id}"
                    if release_id
                    else " without an active release"
                )
            ),
        )

        connection.execute("COMMIT")

        return {
            "accepted": True,
            "duplicate": False,
            "id": work_id,
            "status": "QUEUED",
            "release_id": release_id,
        }

    except Exception:
        connection.execute("ROLLBACK")
        raise