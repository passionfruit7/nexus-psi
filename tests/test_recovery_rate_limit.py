import time

from nexus.core.supervisor import Supervisor
from nexus.storage.database import initialize


WORKER_ID = "recovery-rate-test-worker"


def main():
    print("=== NEXUS R11 RECOVERY RATE LIMIT TEST ===")

    initialize()

    supervisor = Supervisor(
        [WORKER_ID],
        max_restarts=3,
        restart_window_seconds=60,
        base_backoff_seconds=0.2,
        max_backoff_seconds=0.8,
    )

    try:
        supervisor.start_worker(WORKER_ID)

        worker = supervisor.workers[WORKER_ID]

        print(
            f"Initial worker PID: {worker.process.pid}"
        )

        observed_delays = []

        for crash_number in range(1, 4):

            worker = supervisor.workers[WORKER_ID]

            if worker.process is None:
                raise AssertionError(
                    "Worker unexpectedly has no process"
                )

            process = worker.process

            print(
                f"\n--- Crash #{crash_number} "
                f"(PID {process.pid}) ---"
            )

            crash_time = time.time()

            process.kill()
            process.wait()

            supervisor.check_workers()

            restart_time = time.time()

            delay = restart_time - crash_time

            observed_delays.append(delay)

            worker = supervisor.workers[WORKER_ID]

            print(
                f"Observed recovery delay: "
                f"{delay:.3f}s"
            )

            print(
                f"Restart count: "
                f"{worker.restart_count}"
            )

            print(
                f"Worker state: "
                f"{worker.state}"
            )

            if worker.state == "OUT_OF_SERVICE":
                break

        print()
        print("Observed recovery delays:")

        for index, delay in enumerate(
            observed_delays,
            start=1,
        ):
            print(
                f"Restart {index}: "
                f"{delay:.3f}s"
            )

        assert len(observed_delays) == 3, (
            "Expected three restart attempts"
        )

        # The configured backoff is:
        #
        # restart 1 -> 0.2s
        # restart 2 -> 0.4s
        # restart 3 -> 0.8s
        #
        # Allow a small tolerance for process/scheduling overhead.

        assert observed_delays[0] >= 0.18, (
            "First restart was not sufficiently delayed"
        )

        assert observed_delays[1] >= 0.38, (
            "Second restart did not respect increased backoff"
        )

        assert observed_delays[2] >= 0.78, (
            "Third restart did not respect maximum backoff"
        )

        print()
        print("===================================")
        print("R11 RECOVERY RATE LIMIT TEST PASSED")
        print("===================================")

    finally:
        worker = supervisor.workers[WORKER_ID]

        if worker.process is not None:
            supervisor.stop_worker(WORKER_ID)


if __name__ == "__main__":
    main()