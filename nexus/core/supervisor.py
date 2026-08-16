from dataclasses import dataclass
import subprocess
import sys
import time

from nexus.core.events import record_event
from nexus.storage.database import connect, initialize


@dataclass
class WorkerProcess:
    worker_id: str
    process: subprocess.Popen | None = None

    restart_count: int = 0
    first_restart_at: float | None = None

    state: str = "STOPPED"

    last_start_at: float | None = None
    last_exit_code: int | None = None


class Supervisor:
    """
    Supervises NEXUS worker processes.

    Responsibilities:

    - Start workers
    - Detect unexpected worker exits
    - Recover work that was running when a worker died
    - Restart failed workers
    - Maintain a restart budget
    - Use exponential backoff
    - Stop restarting a worker after the restart budget is exhausted
    """

    def __init__(
        self,
        worker_ids,
        *,
        max_restarts=5,
        restart_window_seconds=60,
        base_backoff_seconds=1,
        max_backoff_seconds=16,
    ):
        self.worker_ids = list(worker_ids)

        self.max_restarts = max_restarts
        self.restart_window_seconds = restart_window_seconds

        self.base_backoff_seconds = base_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds

        self.workers = {
            worker_id: WorkerProcess(
                worker_id=worker_id
            )
            for worker_id in self.worker_ids
        }

        self.running = False

    def start_worker(self, worker_id):
        """
        Start one worker as a separate operating-system process.
        """

        worker = self.workers[worker_id]

        command = [
            sys.executable,
            "-m",
            "nexus.workers.worker",
            "--worker-id",
            worker_id,
        ]

        print(
            f"[supervisor] starting {worker_id}",
            flush=True,
        )

        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
        )

        worker.process = process
        worker.state = "RUNNING"
        worker.last_start_at = time.time()
        worker.last_exit_code = None

        print(
            f"[supervisor] {worker_id} started "
            f"(pid={process.pid})",
            flush=True,
        )

    def stop_worker(self, worker_id):
        """
        Stop one worker process gracefully.
        """

        worker = self.workers[worker_id]

        if worker.process is None:
            return

        if worker.process.poll() is not None:
            worker.process = None
            worker.state = "STOPPED"
            return

        print(
            f"[supervisor] stopping {worker_id}",
            flush=True,
        )

        worker.process.terminate()

        try:
            worker.process.wait(timeout=5)

        except subprocess.TimeoutExpired:
            print(
                f"[supervisor] {worker_id} did not stop "
                f"gracefully; killing it",
                flush=True,
            )

            worker.process.kill()
            worker.process.wait()

        worker.last_exit_code = worker.process.returncode
        worker.process = None
        worker.state = "STOPPED"

    def start_all(self):
        """
        Start every configured worker.
        """

        for worker_id in self.worker_ids:
            self.start_worker(worker_id)

    def stop_all(self):
        """
        Stop every configured worker.
        """

        for worker_id in self.worker_ids:
            self.stop_worker(worker_id)

    def _restart_allowed(self, worker):
        """
        Determine whether another restart is allowed.

        Restart attempts are counted within a failure window.
        """

        now = time.time()

        if worker.first_restart_at is None:
            worker.first_restart_at = now
            worker.restart_count = 0

        elif (
            now - worker.first_restart_at
            > self.restart_window_seconds
        ):
            worker.first_restart_at = now
            worker.restart_count = 0

        if worker.restart_count >= self.max_restarts:
            return False

        return True

    def _backoff_seconds(self, worker):
        """
        Calculate exponential restart backoff.
        """

        delay = self.base_backoff_seconds * (
            2 ** worker.restart_count
        )

        return min(
            delay,
            self.max_backoff_seconds,
        )

    def recover_worker_jobs(self, worker_id):
        """
        Recover work that was RUNNING when a worker died.

        The unfinished attempt is marked as WORKER_CRASHED,
        and the work is returned to QUEUED so that another
        attempt can execute it.
        """

        connection = connect()

        try:
            connection.execute("BEGIN IMMEDIATE")

            rows = connection.execute(
                """
                SELECT
                    id,
                    attempt_count,
                    max_attempts,
                    status
                FROM work_items
                WHERE worker_id = ?
                  AND status = 'RUNNING'
                """,
                (worker_id,),
            ).fetchall()

            recovered = []

            for row in rows:
                work_id = row["id"]
                attempt_number = row["attempt_count"]
                max_attempts = row["max_attempts"]

                now = time.time()

                # Mark the unfinished attempt as failed because
                # its worker disappeared before completion.
                connection.execute(
                    """
                    UPDATE attempts
                    SET
                        finished_at = ?,
                        outcome = 'WORKER_CRASHED',
                        error = ?
                    WHERE work_id = ?
                      AND attempt_number = ?
                      AND finished_at IS NULL
                    """,
                    (
                        now,
                        (
                            f"Worker {worker_id} exited "
                            "before completing work"
                        ),
                        work_id,
                        attempt_number,
                    ),
                )

                # Return the work to QUEUED so another worker
                # can make another attempt.
                connection.execute(
                    """
                    UPDATE work_items
                    SET
                        status = 'QUEUED',
                        worker_id = NULL,
                        updated_at = ?,
                        next_attempt_at = ?,
                        last_error = ?,
                        final_reason = NULL
                    WHERE id = ?
                      AND status = 'RUNNING'
                    """,
                    (
                        now,
                        now,
                        f"worker_crashed:{worker_id}",
                        work_id,
                    ),
                )

                record_event(
                    connection,
                    "WORK_RECOVERED",
                    subject_type="work",
                    subject_id=work_id,
                    work_id=work_id,
                    worker_id=worker_id,
                    severity="WARNING",
                    decision="REQUEUE",
                    reason="worker_crashed",
                    message=(
                        f"Work {work_id} recovered after "
                        f"worker {worker_id} crashed"
                    ),
                )

                recovered.append(work_id)

            record_event(
                connection,
                "WORKER_CRASHED",
                subject_type="worker",
                subject_id=worker_id,
                worker_id=worker_id,
                severity="ERROR",
                decision="RECOVER",
                reason="unexpected_process_exit",
                message=(
                    f"Worker {worker_id} exited unexpectedly; "
                    f"recovered {len(recovered)} work item(s)"
                ),
            )

            connection.execute("COMMIT")

            return recovered

        except Exception:
            connection.execute("ROLLBACK")
            raise

        finally:
            connection.close()

    def check_workers(self):
        """
        Inspect all worker processes.

        If a worker exited unexpectedly:

        1. Record/recover its unfinished work.
        2. Check the restart budget.
        3. Apply exponential backoff.
        4. Restart the worker if allowed.
        5. Otherwise mark it OUT_OF_SERVICE.
        """

        for worker_id in self.worker_ids:
            worker = self.workers[worker_id]

            if worker.process is None:
                continue

            exit_code = worker.process.poll()

            # None means the process is still alive.
            if exit_code is None:
                continue

            worker.last_exit_code = exit_code
            worker.process = None

            print(
                f"[supervisor] {worker_id} exited "
                f"with code {exit_code}",
                flush=True,
            )

            # Recover any work that was RUNNING under this worker.
            recovered = self.recover_worker_jobs(
                worker_id
            )

            if recovered:
                print(
                    f"[supervisor] recovered "
                    f"{len(recovered)} work item(s) "
                    f"from {worker_id}",
                    flush=True,
                )

            # Check whether another restart is permitted.
            if not self._restart_allowed(worker):
                worker.state = "OUT_OF_SERVICE"

                print(
                    f"[supervisor] {worker_id} is "
                    f"OUT_OF_SERVICE",
                    flush=True,
                )

                continue

            worker.state = "RESTARTING"

            delay = self._backoff_seconds(worker)

            print(
                f"[supervisor] {worker_id} restarting "
                f"in {delay:.1f}s "
                f"(restart "
                f"{worker.restart_count + 1}/"
                f"{self.max_restarts})",
                flush=True,
            )

            time.sleep(delay)

            worker.restart_count += 1

            self.start_worker(worker_id)

    def run(self):
        """
        Run the supervisor loop continuously.
        """

        initialize()

        self.running = True

        self.start_all()

        print(
            "[supervisor] supervision active",
            flush=True,
        )

        try:
            while self.running:
                self.check_workers()
                time.sleep(0.2)

        except KeyboardInterrupt:
            print(
                "[supervisor] stopping",
                flush=True,
            )

        finally:
            self.running = False
            self.stop_all()