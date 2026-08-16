import time

from nexus.core.events import record_event
from nexus.storage.database import connect


DEFAULT_DETECTION_LIMIT_SECONDS = 5.0


class ConsistencyError(Exception):
    """Raised when consistency checking cannot be completed."""


def check_consistency(
    subject_type,
    subject_id,
    left_value,
    right_value,
    *,
    left_source="left",
    right_source="right",
    detection_limit_seconds=DEFAULT_DETECTION_LIMIT_SECONDS,
):
    """
    Compare two independently observed values.

    If the values disagree, NEXUS reports the disagreement
    through a durable structured event.

    This function deliberately does NOT silently repair either
    value. The disagreement remains visible to the operator.
    """

    if not subject_type:
        raise ConsistencyError(
            "subject_type is required"
        )

    if not subject_id:
        raise ConsistencyError(
            "subject_id is required"
        )

    if detection_limit_seconds <= 0:
        raise ConsistencyError(
            "detection_limit_seconds must be positive"
        )

    detected_at = time.time()

    agrees = (
        left_value == right_value
    )

    if agrees:
        return {
            "consistent": True,
            "disagreement": False,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "detected_at": detected_at,
            "detection_time_seconds": 0.0,
        }

    connection = connect()

    try:
        record_event(
            connection,
            "CONSISTENCY_DISAGREEMENT",
            subject_type=subject_type,
            subject_id=subject_id,
            severity="ERROR",
            decision="REPORT",
            reason="value_mismatch",
            before={
                "source": left_source,
                "value": left_value,
            },
            after={
                "source": right_source,
                "value": right_value,
            },
            message=(
                f"Consistency disagreement detected for "
                f"{subject_type} {subject_id}: "
                f"{left_source} != {right_source}"
            ),
        )

        return {
            "consistent": False,
            "disagreement": True,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "left_source": left_source,
            "right_source": right_source,
            "left_value": left_value,
            "right_value": right_value,
            "detected_at": detected_at,
            "detection_time_seconds": 0.0,
            "reported": True,
        }

    finally:
        connection.close()