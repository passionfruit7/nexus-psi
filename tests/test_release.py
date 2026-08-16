import uuid

from nexus.core.intake import accept_work
from nexus.core.release_manager import (
    activate_release,
    create_release,
    get_active_release,
    get_release,
    rollback_release,
)
from nexus.storage.database import connect, initialize


def test_r6_release_rollback(suffix):
    print()
    print("=== R6: RELEASE ROLLBACK ===")

    release_a = create_release(
        f"v1.0-{suffix}",
        release_id=f"release-a-{suffix}",
    )

    activate_release(
        release_a["release_id"]
    )

    release_b = create_release(
        f"v2.0-{suffix}",
        release_id=f"release-b-{suffix}",
    )

    activate_release(
        release_b["release_id"]
    )

    active = get_active_release()

    assert active is not None
    assert (
        active["release_id"]
        == release_b["release_id"]
    )

    assert (
        active["previous_release_id"]
        == release_a["release_id"]
    )

    rollback = rollback_release(
        release_b["release_id"],
        reason="r6_test_rollback",
    )

    assert rollback["success"] is True

    active_after = get_active_release()

    assert active_after is not None
    assert (
        active_after["release_id"]
        == release_a["release_id"]
    )

    rolled_back = get_release(
        release_b["release_id"]
    )

    assert rolled_back["status"] == "ROLLED_BACK"

    print("R6 RELEASE ROLLBACK PASSED")


def test_r7_release_attribution(suffix):
    print()
    print("=== R7: RELEASE-TO-BEHAVIOUR ATTRIBUTION ===")

    release_a = create_release(
        f"v3.0-{suffix}",
        release_id=f"release-r7-a-{suffix}",
    )

    activate_release(
        release_a["release_id"]
    )

    work_id = (
        f"r7-work-{suffix}"
    )

    connection = connect()

    try:
        result = accept_work(
            connection,
            work_id,
            "demo",
            {
                "message": "R7 release attribution test"
            },
        )

        print("Accepted work:")
        print(result)

        assert result["accepted"] is True

    finally:
        connection.close()

    connection = connect()

    try:
        work = connection.execute(
            """
            SELECT
                id,
                status,
                release_id
            FROM work_items
            WHERE id = ?
            """,
            (work_id,),
        ).fetchone()

        assert work is not None

        print("Work record:")
        print(dict(work))

        assert (
            work["release_id"]
            == release_a["release_id"]
        )

        attempts = connection.execute(
            """
            SELECT
                work_id,
                attempt_number,
                release_id
            FROM attempts
            WHERE work_id = ?
            ORDER BY attempt_number
            """,
            (work_id,),
        ).fetchall()

        events = connection.execute(
            """
            SELECT
                event_type,
                work_id,
                release_id
            FROM events
            WHERE work_id = ?
            ORDER BY id
            """,
            (work_id,),
        ).fetchall()

    finally:
        connection.close()

    # Work must be attributed to the release that
    # was active when it was accepted.
    assert (
        work["release_id"]
        == release_a["release_id"]
    )

    print("Release attribution:")
    print(
        work["release_id"]
    )

    # Acceptance event must carry the same release.
    accepted_events = [
        dict(event)
        for event in events
        if event["event_type"]
        == "WORK_ACCEPTED"
    ]

    assert accepted_events

    assert (
        accepted_events[0]["release_id"]
        == release_a["release_id"]
    )

    print("Acceptance event:")
    print(
        accepted_events[0]
    )

    print("R7 RELEASE ATTRIBUTION PASSED")


def main():
    initialize()

    print("===================================")
    print("NEXUS RELEASE REQUIREMENT TESTS")
    print("===================================")

    suffix = uuid.uuid4().hex[:6]

    test_r6_release_rollback(
        suffix
    )

    test_r7_release_attribution(
        suffix
    )

    print()
    print("===================================")
    print("R6 + R7 TESTS PASSED")
    print("===================================")


if __name__ == "__main__":
    main()