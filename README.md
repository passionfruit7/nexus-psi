# NEXUS

## Reliable Work Orchestration & Operator Control Plane

NEXUS is a local reliability platform for accepting, executing, retrying, recovering, inspecting, and controlling work.

The project is designed around a simple principle:

> A reliable system should make its state, failures, decisions, recovery, and uncertainty visible.

NEXUS uses durable local state with SQLite and provides an operator dashboard for observing system behaviour.

---

## Project Structure

```text
nexus-suhani/
│
├── .streamlit/
│   └── config.toml
│
├── data/
│   └── nexus.db
│
├── nexus/
│   ├── __init__.py
│   ├── __main__.py
│   │
│   ├── core/
│   │   ├── cache_manager.py
│   │   ├── consistency.py
│   │   ├── degradation.py
│   │   ├── events.py
│   │   ├── intake.py
│   │   ├── order.py
│   │   ├── release_manager.py
│   │   └── supervisor.py
│   │
│   ├── operator/
│   │   ├── beliefs.py
│   │   ├── commands.py
│   │   ├── dashboard.py
│   │   ├── failure_injection.py
│   │   ├── queries.py
│   │   └── runtime.py
│   │
│   ├── services/
│   │   └── cache_store.py
│   │
│   ├── storage/
│   │   ├── database.py
│   │   └── schema.sql
│   │
│   └── workers/
│       └── worker.py
│
├── tests/
│   ├── test_beliefs.py
│   ├── test_cache.py
│   ├── test_consistency.py
│   ├── test_degradation.py
│   ├── test_failure_injection.py
│   ├── test_idempotency.py
│   ├── test_intake.py
│   ├── test_operator_commands.py
│   ├── test_operator_diagnosis.py
│   ├── test_operator_queries.py
│   ├── test_operator_runtime.py
│   ├── test_order.py
│   ├── test_recovery.py
│   ├── test_recovery_rate_limit.py
│   ├── test_release.py
│   ├── test_restart.py
│   ├── test_retries.py
│   └── test_supervisor.py
│
├── .gitignore
├── ACCOUNT.md
├── README.md
└── pyproject.toml
```

---

## Requirements

NEXUS requires:

- Python 3
- A Python virtual environment
- Streamlit for the operator dashboard

The system uses SQLite for local durable state.

No cloud service is required for the local demonstration.

---

## Setup

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the project:

```bash
pip install -e .
```

If Streamlit is not installed:

```bash
pip install streamlit
```

Initialize the database:

```bash
python -c "from nexus.storage.database import initialize; initialize()"
```

The local database is stored in:

```text
data/nexus.db
```

---

## Running NEXUS

Start the platform:

```bash
python -m scripts.start
```

Then open another terminal from the repository root and activate the environment:

```bash
source .venv/bin/activate
```

Start the operator dashboard:

```bash
streamlit run nexus/operator/dashboard.py
```

The dashboard provides visibility into the current durable state of the system.

---

## Operator Dashboard

The dashboard exposes the main operational state of NEXUS.

It includes:

- System Health
- Work Queue
- Retrying Work
- Work Inspection
- Attempts
- Event Timeline
- Recent Failures
- Recent Events

The System Health section shows:

```text
Total Work
Queued
Running
Succeeded
Dead Lettered
```

The Work Queue separates work by state:

```text
Queued
Running
Succeeded
Dead Lettered
```

The Inspect Work section allows an operator to enter a Work ID and inspect its durable record, attempts, and event history.

The dashboard is intended to make the system explainable without requiring the operator to reconstruct state manually from raw logs.

---

## Reliability Behaviour

NEXUS implements and demonstrates the following reliability behaviours.

### R-01 — Accepted work is safe

Accepted work is persisted as durable platform state rather than existing only in process memory.

### R-02 — Every piece of work ends somewhere

Work has explicit lifecycle states including queued, running, succeeded, and dead-lettered.

### R-03 — Doing it twice is harmless

Durable deduplication records support idempotent work handling.

Run:

```bash
python -m tests.test_idempotency
```

### R-04 — Trying again has a limit

Retryable failures are retried only while attempts remain.

Run:

```bash
python -m tests.test_retries
```

### R-05 — You can ask about the past

Attempts and structured events are persisted so the history of a work item can be inspected.

Run:

```bash
python -m tests.test_operator_diagnosis
```

### R-06 — Changes can be undone

Release management supports activation and rollback.

Run:

```bash
python -m tests.test_release
```

### R-07 — Changes are linked to what followed

Release and work state are associated through release identifiers and structured events.

### R-08 — Disagreements are found

NEXUS detects conflicting information instead of silently choosing between disagreeing values.

Run:

```bash
python -m tests.test_consistency
```

### R-09 — Copied values carry their age

Cached values record their creation time and are refused once they exceed their allowed age.

Run:

```bash
python -m tests.test_cache
```

The test demonstrates:

```text
Fresh value
    ↓
served

Expired value
    ↓
refused

Expired value
    ↓
still observable
```

### R-10 — Degrading is honest

When a dependency is unavailable, NEXUS can expose a fallback while explicitly marking the system as degraded.

Run:

```bash
python -m tests.test_degradation
```

The important distinction is:

```text
source = live
status = HEALTHY
```

versus:

```text
source = last-known-value
status = DEGRADED
```

Fallback information must not be presented as live information.

### R-11 — Recovery does no harm

Worker recovery is rate-limited and restart attempts are bounded.

Run:

```bash
python -m tests.test_recovery
python -m tests.test_recovery_rate_limit
python -m tests.test_restart
```

Repeated worker crashes eventually exhaust the restart budget and place the worker out of service.

### R-12 — A guess within ninety seconds

The operator-facing diagnosis and event history are designed to provide enough information for an engineer to form a sensible first hypothesis quickly.

Run:

```bash
python -m tests.test_operator_diagnosis
```

### R-13 — Order is only claimed when known

NEXUS separates explicitly supported ordering information from display adjacency.

Run:

```bash
python -m tests.test_order
```

When evidence is insufficient, the system reports that order is unknown rather than guessing.

### R-14 — The platform can be asked about itself

NEXUS can report its own durable work state, release state, and recent events.

Run:

```bash
python -m tests.test_beliefs
```

### R-15 — Failures can be triggered

Deterministic failure injection provides a deliberate way to demonstrate failure and retry behaviour.

Run:

```bash
python -m tests.test_failure_injection --worker-id failure-test-worker
```

A work body can request a limited number of failures:

```json
{
  "fail_attempts": 2
}
```

This produces the sequence:

```text
Attempt 1 → FAIL
Attempt 2 → FAIL
Attempt 3 → SUCCESS
```

Permanent failure can be requested with:

```json
{
  "always_fail": true
}
```

---

## Release Rollback

Release state is persisted separately from worker state.

The release manager supports:

```text
create_release()
activate_release()
get_active_release()
get_release()
rollback_release()
list_releases()
```

A rollback restores the release that was active immediately before the current release.

Run:

```bash
python -m tests.test_release
```

The test verifies:

```text
Release A → ACTIVE
Release B → ACTIVE
Rollback B
Release A → ACTIVE
Release B → ROLLED_BACK
```

---

## Worker Recovery

Workers are supervised by the NEXUS supervisor.

A worker crash does not automatically mean the associated work succeeded.

Recovery can:

```text
detect worker failure
        ↓
recover affected work
        ↓
make work eligible again
        ↓
create a new attempt
```

Restart behaviour is bounded by a restart budget and recovery is rate-limited to avoid uncontrolled restart loops.

---

## Cache Freshness

Cached values contain age information.

Conceptually:

```text
age = current_time - created_at
```

A cached value is served only while:

```text
age <= maximum_allowed_age
```

Expired values remain observable for diagnosis but are not silently presented as current.

---

## Honest Degradation

NEXUS distinguishes between live dependency information and fallback information.

Healthy:

```json
{
  "inventory": 42,
  "source": "live"
}
```

Degraded:

```json
{
  "fallback": {
    "inventory": 40,
    "source": "last-known-value"
  },
  "reason": "dependency_unavailable",
  "dependency_available": false
}
```

This makes the loss of live dependency information explicit.

---

## Order Certainty

NEXUS does not infer ordering merely because records appear next to one another.

Known ordering is represented when explicit evidence exists.

Without sufficient evidence:

```text
order_known = false
```

This prevents the operator interface from turning incomplete information into false certainty.

---

## Operator Commands

The operator layer supports explicit commands including:

```text
start_worker
stop_worker
restart_worker
requeue_work
retry_dead_letter
```

Run:

```bash
python -m tests.test_operator_commands
```

Operator actions are recorded as structured events so manual intervention remains observable.

---

## Durable State

SQLite is used as the local durable state store.

Important persistent records include:

```text
work_items
attempts
dedupe_records
events
releases
```

A work item records information such as:

```text
id
type
status
attempt_count
max_attempts
created_at
updated_at
next_attempt_at
worker_id
release_id
accepted_at
completed_at
last_error
final_reason
```

Attempts record execution history.

Events record significant state changes, decisions, reasons, and messages.

This provides the evidence used by the operator dashboard.

---

## Test Suite

The repository contains executable tests for the reliability behaviours.

Run individual tests from the repository root:

```bash
python -m tests.test_intake
python -m tests.test_retries
python -m tests.test_idempotency
python -m tests.test_recovery
python -m tests.test_recovery_rate_limit
python -m tests.test_restart
python -m tests.test_release
python -m tests.test_consistency
python -m tests.test_cache
python -m tests.test_degradation
python -m tests.test_order
python -m tests.test_failure_injection --worker-id failure-test-worker
python -m tests.test_operator_commands
python -m tests.test_operator_queries
python -m tests.test_operator_runtime
python -m tests.test_operator_diagnosis
python -m tests.test_supervisor
python -m tests.test_beliefs
```

A successful test prints a corresponding `TEST PASSED` message.

---

## Resetting Local State

To reset the local demonstration database:

```bash
python -m scripts.reset
```

Only use this when the current local state is no longer needed.

The database is intentionally ignored by Git.

---

## Git Hygiene

The repository should not commit:

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

These are covered by `.gitignore`.

Source code, tests, configuration, documentation, and project metadata should remain tracked.

---

## Handover Checklist

Before final submission:

```text
[ ] Create a clean virtual environment
[ ] Install the project
[ ] Initialize the database
[ ] Start NEXUS
[ ] Start the dashboard
[ ] Verify the dashboard loads
[ ] Run the reliability tests
[ ] Verify retry behaviour
[ ] Verify dead-letter behaviour
[ ] Verify worker recovery
[ ] Verify restart budget
[ ] Verify recovery rate limiting
[ ] Verify cache expiration
[ ] Verify honest degradation
[ ] Verify consistency detection
[ ] Verify order certainty
[ ] Verify release rollback
[ ] Verify platform beliefs
[ ] Verify failure injection
[ ] Inspect attempts and events in the dashboard
[ ] Verify no secrets are committed
[ ] Verify local database files are ignored
```

---

## Scope and Limitations

NEXUS is a local reliability demonstration platform.

It is not presented as a production distributed orchestration system.

The implementation uses local SQLite storage and local worker processes. The dashboard is an operator interface for demonstration and inspection.

Passing the executable tests demonstrates the implemented behaviours under the tested scenarios. It does not constitute a guarantee against every possible hardware, operating-system, network, or distributed-system failure.

---

## Final Principle

NEXUS is built around explicit state and observable behaviour.

It does not assume that a running process means successful work.

It does not assume that a cached value is current.

It does not assume that adjacent records are ordered.

It does not silently hide failures.

It records what happened, what decision was made, and why.

The intended evaluation flow is:

```text
START
  ↓
RUN NEXUS
  ↓
OPEN OPERATOR DASHBOARD
  ↓
TRIGGER / OBSERVE FAILURE
  ↓
INSPECT DURABLE STATE
  ↓
VERIFY RECOVERY / RETRY / ROLLBACK
```
