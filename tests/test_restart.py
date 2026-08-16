import time

from nexus.core.supervisor import Supervisor
from nexus.storage.database import initialize


def main():
    print("=== NEXUS RESTART BUDGET TEST ===")

    initialize()

    supervisor = Supervisor(
        ["restart-test-worker"],
        max_restarts=3,
        restart_window_seconds=60,
        base_backoff_seconds=0.1,
        max_backoff_seconds=0.2,
    )

    worker_id = "restart-test-worker"

    try:
        supervisor.start_worker(worker_id)

        worker = supervisor.workers[worker_id]

        print(
            f"Initial worker PID: {worker.process.pid}"
        )

        # Deliberately crash the worker repeatedly.
        #
        # We do this faster than the restart window so
        # the restart budget cannot reset.
        for crash_number in range(1, 6):
            worker = supervisor.workers[worker_id]

            if worker.process is None:
                print(
                    f"Worker has no process after "
                    f"crash #{crash_number}"
                )
                break

            process = worker.process

            print(
                f"\n--- Forcing crash #{crash_number} "
                f"(PID {process.pid}) ---"
            )

            process.kill()
            process.wait()

            supervisor.check_workers()

            worker = supervisor.workers[worker_id]

            print(
                "State:",
                worker.state,
            )

            print(
                "Restart count:",
                worker.restart_count,
            )

            if worker.state == "OUT_OF_SERVICE":
                break

            time.sleep(0.1)

        worker = supervisor.workers[worker_id]

        print("\nFinal worker state:")
        print(worker)

        assert worker.state == "OUT_OF_SERVICE", (
            "Worker should become OUT_OF_SERVICE "
            "after exhausting restart budget"
        )

        assert worker.restart_count == 3, (
            "Worker should have consumed exactly "
            "3 restart attempts"
        )

        print()
        print("===================================")
        print("RESTART BUDGET TEST PASSED")
        print("===================================")

    finally:
        worker = supervisor.workers[worker_id]

        if worker.process is not None:
            supervisor.stop_worker(worker_id)


if __name__ == "__main__":
    main()