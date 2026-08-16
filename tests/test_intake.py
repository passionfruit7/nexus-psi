from nexus.core.intake import accept_work
from nexus.storage.database import connect, initialize


def main():
    initialize()

    connection = connect()

    try:
        result = accept_work(
            connection,
            work_id="test-job-001",
            work_type="demo",
            body={
                "message": "Hello NEXUS",
                "number": 1,
            },
        )

        print("Acceptance result:")
        print(result)

        row = connection.execute(
            """
            SELECT
                id,
                type,
                body_json,
                status,
                attempt_count,
                max_attempts,
                accepted_at
            FROM work_items
            WHERE id = ?
            """,
            ("test-job-001",),
        ).fetchone()

        print("\nDatabase record:")
        print(dict(row))

        event = connection.execute(
            """
            SELECT
                event_type,
                work_id,
                decision,
                reason,
                message
            FROM events
            WHERE work_id = ?
                AND event_type = 'WORK_ACCEPTED'
            ORDER BY id DESC
            LIMIT 1
            """,
            ("test-job-001",),
        ).fetchone()

        print("\nAcceptance event:")
        print(dict(event))

    finally:
        connection.close()


if __name__ == "__main__":
    main()