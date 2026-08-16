from nexus.core.supervisor import Supervisor


def main():
    supervisor = Supervisor(
        ["worker-1"],
        max_restarts=5,
        restart_window_seconds=60,
        base_backoff_seconds=1,
        max_backoff_seconds=4,
    )

    supervisor.run()


if __name__ == "__main__":
    main()