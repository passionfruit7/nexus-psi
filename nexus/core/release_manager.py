import time
import uuid

from nexus.core.events import record_event
from nexus.storage.database import connect


class ReleaseError(Exception):
    """Raised when a release operation cannot be completed safely."""


def create_release(
    version,
    *,
    release_id=None,
):
    """
    Create a new inactive release.

    A release is not considered active until activate_release()
    is called.
    """

    if not version:
        raise ReleaseError(
            "version is required"
        )

    release_id = release_id or (
        f"rel-{uuid.uuid4().hex[:8]}"
    )

    now = time.time()

    connection = connect()

    try:
        connection.execute("BEGIN IMMEDIATE")

        existing = connection.execute(
            """
            SELECT release_id
            FROM releases
            WHERE release_id = ?
            """,
            (release_id,),
        ).fetchone()

        if existing is not None:
            connection.execute("ROLLBACK")

            raise ReleaseError(
                f"Release already exists: {release_id}"
            )

        connection.execute(
            """
            INSERT INTO releases (
                release_id,
                version,
                status,
                previous_release_id,
                created_at,
                activated_at,
                rolled_back_at,
                rollback_reason
            )
            VALUES (
                ?,
                ?,
                'CREATED',
                NULL,
                ?,
                NULL,
                NULL,
                NULL
            )
            """,
            (
                release_id,
                version,
                now,
            ),
        )

        record_event(
            connection,
            "RELEASE_CREATED",
            subject_type="release",
            subject_id=release_id,
            release_id=release_id,
            severity="INFO",
            decision="CREATE",
            reason="release_prepared",
            after={
                "release_id": release_id,
                "version": version,
                "status": "CREATED",
            },
            message=(
                f"Release {release_id} "
                f"({version}) created"
            ),
        )

        connection.execute("COMMIT")

        return {
            "release_id": release_id,
            "version": version,
            "status": "CREATED",
        }

    except Exception:
        try:
            connection.execute("ROLLBACK")
        except Exception:
            pass
        raise

    finally:
        connection.close()


def get_active_release():
    """
    Return the currently active release, or None.
    """

    connection = connect()

    try:
        row = connection.execute(
            """
            SELECT
                release_id,
                version,
                status,
                previous_release_id,
                created_at,
                activated_at,
                rolled_back_at,
                rollback_reason
            FROM releases
            WHERE status = 'ACTIVE'
            ORDER BY activated_at DESC
            LIMIT 1
            """
        ).fetchone()

        return dict(row) if row else None

    finally:
        connection.close()


def get_release(release_id):
    """
    Return one release by ID.
    """

    connection = connect()

    try:
        row = connection.execute(
            """
            SELECT
                release_id,
                version,
                status,
                previous_release_id,
                created_at,
                activated_at,
                rolled_back_at,
                rollback_reason
            FROM releases
            WHERE release_id = ?
            """,
            (release_id,),
        ).fetchone()

        return dict(row) if row else None

    finally:
        connection.close()


def activate_release(release_id):
    """
    Activate a release.

    If another release is active, it becomes the previous release
    so that the new release can later be rolled back in one action.
    """

    if not release_id:
        raise ReleaseError(
            "release_id is required"
        )

    connection = connect()

    try:
        connection.execute("BEGIN IMMEDIATE")

        release = connection.execute(
            """
            SELECT
                release_id,
                version,
                status
            FROM releases
            WHERE release_id = ?
            """,
            (release_id,),
        ).fetchone()

        if release is None:
            connection.execute("ROLLBACK")

            raise ReleaseError(
                f"Unknown release: {release_id}"
            )

        if release["status"] == "ACTIVE":
            connection.execute("ROLLBACK")

            return {
                "success": True,
                "release_id": release_id,
                "status": "ACTIVE",
                "previous_release_id": None,
                "already_active": True,
            }

        current = connection.execute(
            """
            SELECT
                release_id,
                version
            FROM releases
            WHERE status = 'ACTIVE'
            ORDER BY activated_at DESC
            LIMIT 1
            """
        ).fetchone()

        previous_release_id = (
            current["release_id"]
            if current is not None
            else None
        )

        now = time.time()

        if current is not None:
            connection.execute(
                """
                UPDATE releases
                SET status = 'SUPERSEDED'
                WHERE release_id = ?
                AND status = 'ACTIVE'
                """,
                (current["release_id"],),
            )

        connection.execute(
            """
            UPDATE releases
            SET
                status = 'ACTIVE',
                previous_release_id = ?,
                activated_at = ?,
                rolled_back_at = NULL,
                rollback_reason = NULL
            WHERE release_id = ?
            """,
            (
                previous_release_id,
                now,
                release_id,
            ),
        )

        record_event(
            connection,
            "RELEASE_ACTIVATED",
            subject_type="release",
            subject_id=release_id,
            release_id=release_id,
            severity="INFO",
            decision="ACTIVATE",
            reason="operator_release",
            before={
                "active_release_id": (
                    previous_release_id
                )
            },
            after={
                "active_release_id": release_id
            },
            message=(
                f"Release {release_id} "
                f"({release['version']}) activated"
            ),
        )

        connection.execute("COMMIT")

        return {
            "success": True,
            "release_id": release_id,
            "status": "ACTIVE",
            "previous_release_id": previous_release_id,
            "already_active": False,
        }

    except Exception:
        try:
            connection.execute("ROLLBACK")
        except Exception:
            pass
        raise

    finally:
        connection.close()


def rollback_release(
    release_id,
    *,
    reason="operator_rollback",
):
    """
    Roll back an active release to the release that was active
    immediately before it.

    This is the core R6 operation.

    One rollback action restores the previous active release.
    """

    if not release_id:
        raise ReleaseError(
            "release_id is required"
        )

    connection = connect()

    try:
        connection.execute("BEGIN IMMEDIATE")

        release = connection.execute(
            """
            SELECT
                release_id,
                version,
                status,
                previous_release_id
            FROM releases
            WHERE release_id = ?
            """,
            (release_id,),
        ).fetchone()

        if release is None:
            connection.execute("ROLLBACK")

            raise ReleaseError(
                f"Unknown release: {release_id}"
            )

        if release["status"] != "ACTIVE":
            connection.execute("ROLLBACK")

            raise ReleaseError(
                f"Release {release_id} is not active"
            )

        previous_release_id = (
            release["previous_release_id"]
        )

        if previous_release_id is None:
            connection.execute("ROLLBACK")

            raise ReleaseError(
                f"Release {release_id} has no previous "
                "release to roll back to"
            )

        previous = connection.execute(
            """
            SELECT
                release_id,
                version,
                status
            FROM releases
            WHERE release_id = ?
            """,
            (previous_release_id,),
        ).fetchone()

        if previous is None:
            connection.execute("ROLLBACK")

            raise ReleaseError(
                "Previous release no longer exists: "
                f"{previous_release_id}"
            )

        now = time.time()

        connection.execute(
            """
            UPDATE releases
            SET
                status = 'ROLLED_BACK',
                rolled_back_at = ?,
                rollback_reason = ?
            WHERE release_id = ?
            AND status = 'ACTIVE'
            """,
            (
                now,
                reason,
                release_id,
            ),
        )

        connection.execute(
            """
            UPDATE releases
            SET
                status = 'ACTIVE',
                activated_at = ?
            WHERE release_id = ?
            """,
            (
                now,
                previous_release_id,
            ),
        )

        record_event(
            connection,
            "RELEASE_ROLLED_BACK",
            subject_type="release",
            subject_id=release_id,
            release_id=release_id,
            severity="WARNING",
            decision="ROLLBACK",
            reason=reason,
            before={
                "active_release_id": release_id
            },
            after={
                "active_release_id": previous_release_id
            },
            message=(
                f"Release {release_id} rolled back "
                f"to {previous_release_id}"
            ),
        )

        connection.execute("COMMIT")

        return {
            "success": True,
            "rolled_back_release": release_id,
            "restored_release": previous_release_id,
            "restored_version": previous["version"],
            "status": "ROLLED_BACK",
        }

    except Exception:
        try:
            connection.execute("ROLLBACK")
        except Exception:
            pass
        raise

    finally:
        connection.close()


def list_releases(limit=20):
    """
    Return recent releases for the operator view.
    """

    connection = connect()

    try:
        rows = connection.execute(
            """
            SELECT
                release_id,
                version,
                status,
                previous_release_id,
                created_at,
                activated_at,
                rolled_back_at,
                rollback_reason
            FROM releases
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()