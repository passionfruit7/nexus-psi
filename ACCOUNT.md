# NEXUS — Account / Handover Notes

## Project

NEXUS — Reliable Work Orchestration & Operator Control Plane

NEXUS is a local reliability platform designed to demonstrate durable work state, bounded retries, worker recovery, operator diagnosis, release rollback, cache freshness, honest degradation, order certainty, and deterministic failure injection.

The project is implemented as a local Python application using SQLite for durable state and Streamlit for the operator dashboard.

---

## Repository

The project root is:

```text
nexus-suhani/
```

Main areas:

```text
nexus/
    core/       Reliability and state-management logic
    operator/   Operator controls, queries, beliefs, and dashboard
    services/   Supporting services
    storage/    SQLite database and schema
    workers/    Worker execution

tests/          Executable requirement tests
scripts/        Startup, reset, seed, demo, and stop utilities
```

The main operator dashboard is:

```text
nexus/operator/dashboard.py
```

The durable database is:

```text
data/nexus.db
```

The database is local runtime state and should not be committed to Git.

---

## Environment

The project was developed locally using Python and a virtual environment.

Create the environment with:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the project:

```bash
pip install -e .
```

The dashboard requires Streamlit:

```bash
pip install streamlit
```

Initialize the database:

```bash
python -c "from nexus.storage.database import initialize; initialize()"
```

---

## Running the Project

From the repository root:

```bash
source .venv/bin/activate
```

Start NEXUS:

```bash
python -m scripts.start
```

In another terminal, start the dashboard:

```bash
source .venv/bin/activate
streamlit run nexus/operator/dashboard.py
```

The dashboard is the main operator-facing interface.

---

## Dashboard

The dashboard currently exposes:

```text
System Health
Work Queue
Retrying Work
Inspect Work
Attempts
Event Timeline
Recent Failures
Recent Events
```

System Health reports:

```text
Total Work
Queued
Running
Succeeded
Dead Lettered
```

Work can be inspected by entering its Work ID.

The inspection view exposes the durable work record, attempt history, and structured event timeline.

The dashboard is intended to make system behaviour understandable without requiring direct database inspection.

---

## Reliability Requirements

The project has executable tests covering the major requirements.

R-01 — Accepted work is safe.

R-02 — Every piece of work ends somewhere.

R-03 — Doing it twice is harmless.

R-04 — Trying again has a limit.

R-05 — You can ask about the past.

R-06 — Changes can be undone.

R-07 — Changes are linked to what followed.

R-08 — Disagreements are found.

R-09 — Copied values carry their age.

R-10 — Degrading is honest.

R-11 — Recovery does no harm.

R-12 — A guess within ninety seconds.

R-13 — Order is only claimed when known.

R-14 — The platform can be asked about itself.

R-15 — Failures can be triggered.

---

## Verified Test Areas

The following behaviours have been exercised during development:

```text
Retry behaviour
Dead-letter behaviour
Idempotency
Worker recovery
Recovery rate limiting
Restart budget
Release activation and rollback
Cache age tracking
Expired cache refusal
Honest degradation
Consistency disagreement detection
Order certainty / no order guessing
Platform beliefs
Operator commands
Operator diagnosis
Failure injection
```

Representative commands:

```bash
python -m tests.test_retries
python -m tests.test_idempotency
python -m tests.test_recovery
python -m tests.test_recovery_rate_limit
python -m tests.test_restart
python -m tests.test_release
python -m tests.test_cache
python -m tests.test_degradation
python -m tests.test_consistency
python -m tests.test_order
python -m tests.test_beliefs
python -m tests.test_operator_commands
python -m tests.test_operator_diagnosis
python -m tests.test_operator_queries
python -m tests.test_operator_runtime
python -m tests.test_supervisor
```

Failure injection is run with a required worker ID:

```bash
python -m tests.test_failure_injection --worker-id failure-test-worker
```

A successful scenario prints a corresponding `TEST PASSED` message.

---

## Important Demonstrated Behaviours

### Retry and failure

A work item can be configured to fail a fixed number of attempts:

```json
{
  "fail_attempts": 2
}
```

Expected sequence:

```text
Attempt 1 → FAILED
Attempt 2 → FAILED
Attempt 3 → SUCCESS
```

Permanent failure can be demonstrated with:

```json
{
  "always_fail": true
}
```

The work eventually becomes `DEAD_LETTERED` after its retry budget is exhausted.

### Worker recovery

Workers are supervised by the Supervisor.

Repeated crashes trigger restart behaviour with backoff and a bounded restart budget.

Once the restart budget is exhausted, the worker becomes:

```text
OUT_OF_SERVICE
```

### Release rollback

Release management supports:

```text
create_release()
activate_release()
get_active_release()
get_release()
rollback_release()
list_releases()
```

The R-06 test verifies that activating a newer release records the previous release and that a rollback restores that previous active release.

### Cache freshness

Cached values carry creation time and maximum age.

Fresh values can be served.

Expired values are refused.

Expired values remain observable for diagnosis.

### Honest degradation

When a dependency is unavailable, NEXUS can use a fallback while explicitly identifying the system as degraded.

The fallback must not be represented as live data.

### Order certainty

NEXUS distinguishes explicit ordering evidence from display adjacency.

When evidence is insufficient, it reports:

```text
order_known = false
```

instead of guessing.

### Platform beliefs

The platform can expose information about its current durable work state, active release, and recent events.

### Failure injection

Failure injection provides a deterministic mechanism to demonstrate failure handling rather than relying on an accidental failure.

---

## Data Model

The primary durable state is stored in SQLite.

Important records include:

```text
work_items
attempts
dedupe_records
events
releases
```

Work items contain lifecycle state, attempt information, worker information, release information, timestamps, and failure information.

Attempts preserve execution history.

Events preserve important decisions, reasons, state transitions, and messages.

This data is what allows the operator dashboard to explain what happened.

---

## Operator Commands

The operator layer supports explicit actions including:

```text
start_worker
stop_worker
restart_worker
requeue_work
retry_dead_letter
```

Operator actions are recorded as events.

This means manual intervention remains visible in the system history.

---

## Resetting the Environment

To reset local demonstration state:

```bash
python -m scripts.reset
```

Do not use the reset command if the current local demonstration state needs to be preserved.

---

## Git / Submission Hygiene

The following should remain untracked:

```text
.venv/
__pycache__/
*.pyc
data/nexus.db
data/nexus.db-wal
data/nexus.db-shm
.DS_Store
.env
```

Check the repository before committing:

```bash
git status
```

The source code, tests, README, project configuration, and other required project files should be tracked.

---

## Clean Handover Procedure

For a final handover, verify the project from a clean environment.

```text
1. Create a new virtual environment.
2. Install the project.
3. Initialize the database.
4. Start NEXUS.
5. Start the dashboard.
6. Verify the dashboard loads.
7. Run the major reliability tests.
8. Verify retry and dead-letter behaviour.
9. Verify worker recovery and restart limits.
10. Verify release rollback.
11. Verify cache freshness.
12. Verify honest degradation.
13. Verify order certainty.
14. Verify platform beliefs.
15. Verify failure injection.
16. Inspect work attempts and events in the dashboard.
17. Check git status.
18. Confirm local runtime/database files are ignored.
```

---

## Known Scope

NEXUS is a local reliability demonstration platform.

It is not intended to claim production-scale distributed orchestration, cloud-scale availability, or complete protection against every possible operating-system, hardware, network, or distributed-system failure.

The executable tests demonstrate the implemented scenarios under the conditions they cover.

SQLite is used as the local durable state store.

The dashboard is an operator demonstration interface, not a production authentication or security boundary.

---

## Final Handover Principle

The core objective of NEXUS is observability of reliable behaviour.

The system should make it possible to understand:

```text
What happened?
Which work was affected?
Which attempt was running?
Why did the platform retry?
Why was work dead-lettered?
What worker was involved?
What release was active?
Was a cached value still fresh?
Was a dependency unavailable?
Was an ordering relationship actually known?
What operator action occurred?
What happened after recovery?
```

The tests provide executable evidence for the implemented reliability behaviours, while the dashboard provides an operator-facing view of the resulting durable state.
