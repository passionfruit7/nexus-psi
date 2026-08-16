# NEXUS

NEXUS is a local **Reliable Work Orchestration & Operator Control Plane**.

It demonstrates how a reliability-oriented platform accepts work, persists its state, retries failures within bounded limits, recovers workers, records decisions, exposes operator state, and makes uncertainty explicit.

The project is designed to be runnable and reviewable from a clean machine rather than relying on undocumented local state.

## What is included

The repository contains the NEXUS platform, executable requirement tests, local scripts, a SQLite durable state store, and a Streamlit operator dashboard.

```text
nexus-suhani/
├── nexus/
│   ├── core/
│   │   ├── cache_manager.py
│   │   ├── consistency.py
│   │   ├── degradation.py
│   │   ├── events.py
│   │   ├── intake.py
│   │   ├── order.py
│   │   ├── release_manager.py
│   │   └── supervisor.py
│   ├── operator/
│   │   ├── beliefs.py
│   │   ├── commands.py
│   │   ├── dashboard.py
│   │   ├── failure_injection.py
│   │   ├── queries.py
│   │   └── runtime.py
│   ├── services/
│   ├── storage/
│   │   ├── database.py
│   │   └── schema.sql
│   └── workers/
│       └── worker.py
├── tests/
├── scripts/
├── .streamlit/
├── README.md
├── ACCOUNT.md
└── .gitignore
```

Runtime database files under `data/` are local state and are intentionally excluded from Git.

## Quick start

Run these commands from the repository root.

```bash
git clone (https://github.com/passionfruit7/nexus-psi)
cd nexus-suhani

python3 -m venv .venv
source .venv/bin/activate

pip install -e .
pip install streamlit

python -c "from nexus.storage.database import initialize; initialize()"
```

Start the NEXUS runtime:

```bash
python -m scripts.start
```

Open a second terminal:

```bash
cd nexus-suhani
source .venv/bin/activate
PYTHONPATH=. python -m streamlit run nexus/operator/dashboard.py
```

The Streamlit URL printed by the command is the operator view.

If the project dependencies are already installed, the shortest dashboard command is:

```bash
streamlit run nexus/operator/dashboard.py
```

## Four-minute reviewer walkthrough

The reviewer should be able to understand the platform without reading the implementation first.

Start the platform and dashboard using the commands above.

On the dashboard, first look at **System Health**. It shows the current durable work state: total work, queued work, running work, succeeded work, and dead-lettered work.

Next look at **Work Queue**. The tabs separate queued, running, succeeded, and dead-lettered work.

To inspect one item, enter its Work ID in **Inspect Work**. The dashboard shows the durable work record, attempts, and event timeline. The event timeline is the quickest way to understand what happened and why.

The **Retrying Work** section shows work waiting for another attempt.

The **Recent Failures** and **Recent Events** sections provide the latest failure and decision history.

## Demonstrating the reliability behaviour

The repository contains executable tests corresponding to the implemented requirements.

Retry and dead-letter behaviour:

```bash
python -m tests.test_retries
```

Idempotency:

```bash
python -m tests.test_idempotency
```

Worker recovery:

```bash
python -m tests.test_recovery
python -m tests.test_recovery_rate_limit
python -m tests.test_restart
```

Release rollback:

```bash
python -m tests.test_release
```

Cache freshness:

```bash
python -m tests.test_cache
```

Consistency and disagreement detection:

```bash
python -m tests.test_consistency
```

Honest degradation:

```bash
python -m tests.test_degradation
```

Order certainty:

```bash
python -m tests.test_order
```

Platform beliefs:

```bash
python -m tests.test_beliefs
```

Operator controls and diagnosis:

```bash
python -m tests.test_operator_commands
python -m tests.test_operator_diagnosis
python -m tests.test_operator_queries
python -m tests.test_operator_runtime
```

Supervisor behaviour:

```bash
python -m tests.test_supervisor
```

Failure injection:

```bash
python -m tests.test_failure_injection --worker-id failure-test-worker
```

Each test prints its observed behaviour and a `TEST PASSED` message when the scenario succeeds.

## Failure demonstrations

A deterministic retry failure can be configured with:

```json
{
  "fail_attempts": 2
}
```

This produces:

```text
attempt 1 → failure
attempt 2 → failure
attempt 3 → success
```

A permanently failing item can be configured with:

```json
{
  "always_fail": true
}
```

The item is retried until its configured attempt budget is exhausted and is then moved to `DEAD_LETTERED`.

Worker recovery can be demonstrated by deliberately terminating a supervised worker. The Supervisor applies bounded restart behaviour and increasing recovery delays. Once the restart budget is exhausted, the worker becomes `OUT_OF_SERVICE`.

Release rollback can be demonstrated by creating and activating release A, creating and activating release B, and rolling B back. The test verifies that A becomes active again.

Cache freshness can be demonstrated with a fresh value and an expired value. A fresh value is served, while an expired value is refused even though the expired value remains observable for diagnosis.

Honest degradation can be demonstrated by making a dependency unavailable. NEXUS exposes the fallback and marks the system as degraded rather than presenting the fallback as live data.

Order certainty can be demonstrated with explicit sequence information and with missing evidence. NEXUS separates known ordering from display adjacency and refuses to infer order when evidence is insufficient.

## R1–R15 coverage

The implemented requirements are exercised through the test suite and operator behaviour.

```text
R-01  Accepted work is safe.
R-02  Every piece of work ends somewhere.
R-03  Doing it twice is harmless.
R-04  Trying again has a limit.
R-05  You can ask about the past.
R-06  Changes can be undone.
R-07  Changes are linked to what followed.
R-08  Disagreements are found.
R-09  Copied values carry their age.
R-10  Degrading is honest.
R-11  Recovery does no harm.
R-12  A guess within ninety seconds.
R-13  Order is only claimed when known.
R-14  The platform can be asked about itself.
R-15  Failures can be triggered.
```

The tests are the primary executable evidence for these behaviours.

## Operator view

The Streamlit dashboard is the main handover interface.

It provides:

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

The dashboard is deliberately backed by the same durable state queried by the platform. It is intended to answer operational questions such as:

```text
What happened?
Which work item was affected?
Which attempt failed?
Why was it retried?
Why was it dead-lettered?
Which worker handled it?
What events were recorded?
What release was active?
```

## Reset and local state

To reset the local demonstration database:

```bash
python -m scripts.reset
```

Use this only when existing demonstration state is no longer required.

The SQLite database is stored under:

```text
data/nexus.db
```

SQLite WAL sidecar files may also appear:

```text
data/nexus.db-wal
data/nexus.db-shm
```

These are runtime artifacts and should not be committed.

## Tests

The complete test directory includes:

```text
test_beliefs.py
test_cache.py
test_consistency.py
test_degradation.py
test_failure_injection.py
test_idempotency.py
test_intake.py
test_operator_commands.py
test_operator_diagnosis.py
test_operator_queries.py
test_operator_runtime.py
test_order.py
test_recovery_rate_limit.py
test_recovery.py
test_release.py
test_restart.py
test_retries.py
test_supervisor.py
```

To run an individual test:

```bash
python -m tests.<test_name>
```

For example:

```bash
python -m tests.test_release
```

## Handover documentation

`ACCOUNT.md` contains the written account required for handover. It is organized around:

```text
Scope
Decisions
Failure behaviour
Limits
Confidence
Next
```

It also records how the system should be run and how its important behaviours can be demonstrated.

## Scope and limitations

NEXUS is a local reliability demonstration platform. It is not presented as a production-scale distributed orchestration system.

SQLite is used as the local durable state store. The Streamlit dashboard is an operator demonstration interface rather than a production authentication or security boundary.

The tests demonstrate the scenarios they explicitly exercise. They should not be interpreted as proof that every possible operating-system, hardware, network, or distributed-system failure is handled.

## Final handover check

Before submission:

```bash
git status
```

Confirm that runtime files such as `.venv/`, `__pycache__/`, `.pyc`, and the SQLite database are ignored.

Then verify the dashboard starts from the README instructions and run the major requirement tests.

The intended handover path is:

```text
Clone
  ↓
Install
  ↓
Initialize
  ↓
Start
  ↓
Open dashboard
  ↓
Run / inspect a scenario
  ↓
Observe durable state and events
```
