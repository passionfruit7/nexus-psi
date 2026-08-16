import time

from nexus.storage.database import connect


def get_platform_beliefs():
    """
    Return the platform's current observable beliefs and
    how recently those beliefs were updated.
    """

    connection = connect()

    try:
        now = time.time()

        work = connection.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'QUEUED'
                    THEN 1 ELSE 0 END) AS queued,
                SUM(CASE WHEN status = 'RUNNING'
                    THEN 1 ELSE 0 END) AS running,
                SUM(CASE WHEN status = 'SUCCEEDED'
                    THEN 1 ELSE 0 END) AS succeeded,
                SUM(CASE WHEN status = 'DEAD_LETTERED'
                    THEN 1 ELSE 0 END) AS dead_lettered,
                MAX(updated_at) AS last_work_update
            FROM work_items
            """
        ).fetchone()

        latest_event = connection.execute(
            """
            SELECT
                event_type,
                occurred_at,
                message
            FROM events
            ORDER BY occurred_at DESC
            LIMIT 1
            """
        ).fetchone()

        latest_release = connection.execute(
            """
            SELECT
                release_id,
                version,
                status,
                activated_at
            FROM releases
            WHERE status = 'ACTIVE'
            ORDER BY activated_at DESC
            LIMIT 1
            """
        ).fetchone()

        last_work_update = (
            work["last_work_update"]
            if work
            else None
        )

        last_event_time = (
            latest_event["occurred_at"]
            if latest_event
            else None
        )

        latest_release_time = (
            latest_release["activated_at"]
            if latest_release
            else None
        )

        return {
            "observed_at": now,

            "work_belief": {
                "total": work["total"] or 0,
                "queued": work["queued"] or 0,
                "running": work["running"] or 0,
                "succeeded": work["succeeded"] or 0,
                "dead_lettered": work["dead_lettered"] or 0,
                "last_update_at": last_work_update,
                "age_seconds": (
                    now - last_work_update
                    if last_work_update
                    else None
                ),
            },

            "latest_event": (
                {
                    "event_type": latest_event["event_type"],
                    "message": latest_event["message"],
                    "occurred_at": last_event_time,
                    "age_seconds": (
                        now - last_event_time
                        if last_event_time
                        else None
                    ),
                }
                if latest_event
                else None
            ),

            "active_release": (
                {
                    "release_id": latest_release["release_id"],
                    "version": latest_release["version"],
                    "status": latest_release["status"],
                    "activated_at": latest_release_time,
                    "age_seconds": (
                        now - latest_release_time
                        if latest_release_time
                        else None
                    ),
                }
                if latest_release
                else None
            ),
        }

    finally:
        connection.close()