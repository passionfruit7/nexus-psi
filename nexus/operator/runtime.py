from nexus.core.supervisor import Supervisor


class OperatorRuntime:
    """
    Runtime bridge between the live NEXUS Supervisor and
    the operator layer.

    The Supervisor remains the source of truth for live
    worker/process state.

    SQLite remains the source of truth for historical
    work and event information.
    """

    def __init__(self, supervisor):
        if not isinstance(supervisor, Supervisor):
            raise TypeError(
                "supervisor must be a Supervisor instance"
            )

        self.supervisor = supervisor

    def get_worker_state(self, worker_id):
        """
        Return the current live state of one worker.
        """

        if not worker_id:
            raise ValueError(
                "worker_id is required"
            )

        worker = self.supervisor.workers.get(
            worker_id
        )

        if worker is None:
            return None

        process = worker.process

        process_alive = False

        if process is not None:
            process_alive = (
                process.poll() is None
            )

        return {
            "worker_id": worker.worker_id,
            "state": worker.state,
            "process_alive": process_alive,
            "pid": (
                process.pid
                if process is not None
                else None
            ),
            "restart_count": worker.restart_count,
            "first_restart_at": (
                worker.first_restart_at
            ),
            "last_start_at": (
                worker.last_start_at
            ),
            "last_exit_code": (
                worker.last_exit_code
            ),
        }

    def get_workers(self):
        """
        Return the current live state of every worker.
        """

        return [
            self.get_worker_state(worker_id)
            for worker_id in self.supervisor.worker_ids
        ]

    def get_runtime_summary(self):
        """
        Return a compact live runtime summary.
        """

        workers = self.get_workers()

        running = 0
        restarting = 0
        stopped = 0
        out_of_service = 0

        for worker in workers:
            state = worker["state"]

            if state == "RUNNING":
                running += 1

            elif state == "RESTARTING":
                restarting += 1

            elif state == "STOPPED":
                stopped += 1

            elif state == "OUT_OF_SERVICE":
                out_of_service += 1

        return {
            "supervision_active": (
                self.supervisor.running
            ),
            "worker_count": len(workers),
            "running": running,
            "restarting": restarting,
            "stopped": stopped,
            "out_of_service": out_of_service,
        }