import time

from nexus.operator.beliefs import get_platform_beliefs
from nexus.storage.database import initialize


def main():
    print("=== NEXUS R14 PLATFORM BELIEFS TEST ===")

    initialize()

    beliefs = get_platform_beliefs()

    print("Platform beliefs:")
    print(beliefs)

    assert "observed_at" in beliefs

    work = beliefs["work_belief"]

    assert "total" in work
    assert "queued" in work
    assert "running" in work
    assert "succeeded" in work
    assert "dead_lettered" in work
    assert "age_seconds" in work

    assert work["age_seconds"] is None or (
        work["age_seconds"] >= 0
    )

    if beliefs["latest_event"] is not None:
        assert (
            beliefs["latest_event"]["age_seconds"]
            >= 0
        )

    if beliefs["active_release"] is not None:
        assert (
            beliefs["active_release"]["age_seconds"]
            >= 0
        )

    observed_at = beliefs["observed_at"]

    assert time.time() >= observed_at

    print()
    print("Observed work state:")
    print(work)

    print()
    print("Latest event:")
    print(beliefs["latest_event"])

    print()
    print("Active release:")
    print(beliefs["active_release"])

    print()
    print("===================================")
    print("R14 PLATFORM BELIEFS TEST PASSED")
    print("===================================")


if __name__ == "__main__":
    main()