import json
import time
import uuid


def record_event(
    connection,
    event_type,
    *,
    subject_type=None,
    subject_id=None,
    work_id=None,
    worker_id=None,
    release_id=None,
    incident_id=None,
    severity="INFO",
    decision=None,
    reason=None,
    before=None,
    after=None,
    message=None,
):
    """
    Record a structured event in the NEXUS event history.
    """

    event_id = str(uuid.uuid4())
    occurred_at = time.time()

    before_json = (
        json.dumps(before, sort_keys=True)
        if before is not None
        else None
    )

    after_json = (
        json.dumps(after, sort_keys=True)
        if after is not None
        else None
    )

    connection.execute(
        """
        INSERT INTO events (
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
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
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
            message,
        ),
    )

    return event_id