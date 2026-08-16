from nexus.core.supervisor import Supervisor
from nexus.operator.runtime import OperatorRuntime
from nexus.operator.queries import (
    get_live_worker_state,
    get_live_workers,
    get_runtime_summary,
)


def main():
    print("=== NEXUS OPERATOR RUNTIME TEST ===")

    supervisor = Supervisor(
        [
            "operator-worker-1",
            "operator-worker-2",
        ]
    )

    runtime = OperatorRuntime(
        supervisor
    )

    # ---------------------------------------------
    # Initial runtime state
    # ---------------------------------------------

    summary = runtime.get_runtime_summary()

    print()
    print("Initial runtime summary:")
    print(summary)

    assert summary["supervision_active"] is False
    assert summary["worker_count"] == 2
    assert summary["running"] == 0
    assert summary["restarting"] == 0
    assert summary["stopped"] == 2
    assert summary["out_of_service"] == 0

    # ---------------------------------------------
    # Individual worker state
    # ---------------------------------------------

    worker = runtime.get_worker_state(
        "operator-worker-1"
    )

    print()
    print("Initial worker state:")
    print(worker)

    assert worker is not None
    assert worker["worker_id"] == (
        "operator-worker-1"
    )
    assert worker["state"] == "STOPPED"
    assert worker["process_alive"] is False
    assert worker["pid"] is None
    assert worker["restart_count"] == 0

    # ---------------------------------------------
    # Unknown worker
    # ---------------------------------------------

    unknown = runtime.get_worker_state(
        "does-not-exist"
    )

    assert unknown is None

    # ---------------------------------------------
    # Query-layer integration
    # ---------------------------------------------

    queried_worker = get_live_worker_state(
        supervisor,
        "operator-worker-2",
    )

    print()
    print("Query-layer worker state:")
    print(queried_worker)

    assert queried_worker is not None
    assert queried_worker["worker_id"] == (
        "operator-worker-2"
    )

    queried_workers = get_live_workers(
        supervisor
    )

    print()
    print("All live workers:")
    print(queried_workers)

    assert len(queried_workers) == 2

    queried_summary = get_runtime_summary(
        supervisor
    )

    print()
    print("Query-layer runtime summary:")
    print(queried_summary)

    assert queried_summary["worker_count"] == 2

    # ---------------------------------------------
    # Start workers
    # ---------------------------------------------

    supervisor.start_all()

    supervisor.running = True

    try:
        summary = runtime.get_runtime_summary()

        print()
        print("Runtime after start:")
        print(summary)

        assert summary["supervision_active"] is True
        assert summary["worker_count"] == 2
        assert summary["running"] == 2

        workers = runtime.get_workers()

        print()
        print("Workers after start:")

        for worker in workers:
            print(worker)

            assert worker["state"] == "RUNNING"
            assert worker["process_alive"] is True
            assert worker["pid"] is not None

        # -----------------------------------------
        # Stop one worker
        # -----------------------------------------

        supervisor.stop_worker(
            "operator-worker-1"
        )

        worker_1 = runtime.get_worker_state(
            "operator-worker-1"
        )

        print()
        print("Worker 1 after stop:")
        print(worker_1)

        assert worker_1["state"] == "STOPPED"
        assert worker_1["process_alive"] is False
        assert worker_1["pid"] is None

        worker_2 = runtime.get_worker_state(
            "operator-worker-2"
        )

        assert worker_2["state"] == "RUNNING"
        assert worker_2["process_alive"] is True

        summary = runtime.get_runtime_summary()

        print()
        print("Runtime after stopping worker 1:")
        print(summary)

        assert summary["running"] == 1
        assert summary["stopped"] == 1

        print()
        print("===================================")
        print("OPERATOR RUNTIME TEST PASSED")
        print("===================================")

    finally:
        supervisor.running = False
        supervisor.stop_all()


if __name__ == "__main__":
    main()