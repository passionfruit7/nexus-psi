# NEXUS — Written Account 

## Scope

NEXUS is a local Reliable Work Orchestration & Operator Control Plane.

The platform was built to demonstrate reliability behaviours that can be observed and tested rather than only described. The implementation covers durable work state, bounded retries, dead-lettering, idempotency, worker supervision and recovery, operator actions, release rollback, cache freshness, consistency disagreements, honest degradation, order certainty, platform beliefs, and deterministic failure injection.

The main platform is under `nexus/`. The operator layer is under `nexus/operator/`. Durable SQLite state is managed under `nexus/storage/`. Worker execution is under `nexus/workers/`. Executable requirement tests are under `tests/`.

The Streamlit application at:

```text
nexus/operator/dashboard.py
```

is the main operator-facing view.

The platform deliberately remains local and understandable. It uses SQLite as its durable state store and does not claim to be a production-scale distributed orchestration system.

The implemented reliability requirements are:

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

The repository contains executable tests for these behaviours and an operator dashboard for observing the resulting durable state.

## Decisions

The system uses durable SQLite records rather than keeping the authoritative work state only in process memory. Work items, attempts, deduplication state, releases, and structured events are persisted so that the operator can inspect what happened after processing or failure.

Work follows explicit lifecycle states. Failed work is not silently discarded. Retryable failures return work to the queue while attempts remain. When the retry budget is exhausted, work becomes `DEAD_LETTERED`.

Retry delays use bounded exponential backoff. This prevents an immediate retry storm while keeping the retry behaviour deterministic enough to demonstrate.

Idempotency is represented through durable deduplication records so repeated handling of the same work can be distinguished from new work.

Worker processes are supervised. Unexpected exits can trigger bounded restarts with backoff. The restart budget prevents an unhealthy worker from being restarted indefinitely. When the budget is exhausted, the worker is placed `OUT_OF_SERVICE`.

Operator actions are explicit rather than arbitrary state edits. The operator command layer supports starting, stopping, restarting, requeueing, and retrying dead-lettered work. These actions are recorded as structured events.

Release management separates creation from activation. A newly created release is not automatically active. Activating a new release records the previously active release, allowing a rollback to restore it.

Cache values retain their age. The platform can inspect an expired value, but an expired value is not served as if it were fresh.

For consistency, the platform reports disagreements rather than silently choosing one value. For ordering, explicit evidence is separated from display adjacency. Missing evidence produces an unknown relationship rather than an invented order.

For dependency failures, the platform uses explicit degraded behaviour. A fallback can be returned, but the response identifies that the dependency was unavailable and that the value is a fallback rather than live data.

The platform also records structured events containing decisions, reasons, before/after state, and messages. This was chosen so that the operator can reconstruct the history of an item instead of relying only on its current status.

## Failure behaviour

Retryable application failures follow the same general lifecycle as ordinary processing failures.

A deterministic test failure can be requested with:

```json
{
  "fail_attempts": 2
}
```

The intended sequence is:

```text
Attempt 1 → FAILED
Attempt 2 → FAILED
Attempt 3 → SUCCESS
```

A permanent failure can be requested with:

```json
{
  "always_fail": true
}
```

The work is retried until the configured maximum number of attempts is reached. It then moves to `DEAD_LETTERED`.

A non-retryable failure can be represented through the failure configuration so the failure becomes terminal instead of entering another retry cycle.

Worker failure is handled separately from application failure. If a supervised worker process exits unexpectedly, the Supervisor observes the exit and can restart it subject to the configured restart budget and backoff. Repeated crashes consume the budget. Once the budget is exhausted, the worker becomes `OUT_OF_SERVICE`.

Release failure is handled through rollback. When release B is active and has a recorded previous release A, a rollback of B restores A as the active release.

For cache failures, an expired value remains inspectable but is refused for serving. The operator can therefore see the stale value without the system misrepresenting it as current.

For dependency failure, NEXUS enters explicit degraded behaviour and exposes the fallback source. The fallback is not presented as live data.

For consistency disagreements, NEXUS reports the disagreement rather than quietly selecting a value.

For insufficient ordering evidence, NEXUS returns an unknown relationship instead of inferring order from display position.

Failure injection is deliberate and deterministic. The purpose is to allow a reviewer to trigger the claimed failure paths and observe their consequences.

## Limits

NEXUS is a local reliability demonstration platform.

SQLite is the durable state store. The design therefore does not claim the characteristics of a multi-node production database or distributed consensus system.

The Streamlit dashboard is an operator demonstration interface. It is not a production authentication, authorization, or security boundary.

The worker supervision and recovery tests exercise process crashes under controlled local conditions. They do not prove recovery from every possible machine, operating-system, network, storage, or infrastructure failure.

The retry and restart budgets are bounded by configuration. A work item that exhausts its retry budget is dead-lettered rather than retried forever. A worker that exhausts its restart budget becomes `OUT_OF_SERVICE`.

Cache freshness depends on the configured maximum age. The system intentionally refuses expired values rather than claiming that they are current.

The order-certainty logic does not infer relationships that are not supported by evidence. Consequently, some sequences can remain partially ordered or unknown.

The platform's evidence is limited to what it records. An operator can only diagnose events, attempts, state transitions, and decisions that are actually persisted.

The executable tests demonstrate the scenarios they cover. Passing them should be understood as evidence for those scenarios, not proof of universal correctness under every failure condition.

## Confidence

Confidence is based primarily on executable demonstrations rather than on code inspection alone.

The repository includes tests for:

```text
retries
idempotency
intake
failure injection
worker supervision
worker recovery
recovery rate limiting
restart budgets
release creation/activation/rollback
cache freshness
consistency disagreements
honest degradation
order certainty
platform beliefs
operator commands
operator diagnosis
operator queries
operator runtime
```

Representative successful demonstrations include:

```text
R-06 RELEASE ROLLBACK TEST PASSED
R-09 CACHE FRESHNESS TEST PASSED
R-11 RECOVERY RATE LIMIT TEST PASSED
R-13 ORDER CERTAINTY TEST PASSED
R-14 PLATFORM BELIEFS TEST PASSED
RESTART BUDGET TEST PASSED
```

The cache tests demonstrated that fresh values are served while expired values are refused and remain observable.

The recovery-rate test demonstrated increasing recovery delays:

```text
Restart 1: approximately 0.2s
Restart 2: approximately 0.4s
Restart 3: approximately 0.8s
```

The restart-budget test demonstrated that repeated crashes consume the restart budget and eventually place the worker in:

```text
OUT_OF_SERVICE
```

The release test demonstrated activation of a newer release followed by rollback to the previous active release.

The order test demonstrated that explicit ordering evidence is retained while display adjacency is not treated as proof of order.

The platform-beliefs test demonstrated that the platform can report information about its own durable work state, active release, and recent events.

Confidence should therefore be strongest for the behaviours directly covered by these executable tests. Areas outside those scenarios remain subject to the limits described above.

## Next

If another six hours were available, the work should be prioritized in this order.

First, perform a clean-machine handover test using only the README instructions. The goal is to confirm that a reviewer who has never seen NEXUS can install it, start it, open the dashboard, and understand the first useful screen without assistance.

Second, run the complete reliability test set again from a clean database and record the final results. This gives a single final evidence pass rather than relying on individual tests run at different development stages.

Third, improve the operator walkthrough so each important requirement has a short, reproducible demonstration path: what command or input triggers it, which state transition should occur, and what the reviewer should look for in the dashboard.

Fourth, review the dashboard for presentation quality and make sure durable state, failures, retries, worker health, releases, and events are visible without unnecessary scrolling or confusing output.

Fifth, add any remaining test coverage only where a requirement currently relies on an implementation path that is not directly exercised by an executable test.

Sixth, perform a final Git hygiene check so runtime databases, virtual environments, Python cache files, and machine-specific files are not committed.

The immediate goal is not to add unrelated functionality. It is to make the existing reliability behaviour easy to reproduce, observe, and evaluate.

## How to run it

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install streamlit
python -c "from nexus.storage.database import initialize; initialize()"
```

Start the runtime:

```bash
python -m scripts.start
```

In another terminal:

```bash
source .venv/bin/activate
streamlit run nexus/operator/dashboard.py
```

Open the URL printed by Streamlit.

The first screen to inspect is **System Health**. Then inspect **Work Queue**, **Retrying Work**, and **Recent Events**. For a particular Work ID, use **Inspect Work** to see the durable record, attempts, and event timeline.

To demonstrate the important behaviours directly, use the executable tests:

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
python -m tests.test_failure_injection --worker-id failure-test-worker
```

A successful scenario prints a corresponding `TEST PASSED` message.

## Reviewer path


The intended reviewer path is:

```text
Clone
  ↓
Create environment
  ↓
Install
  ↓
Initialize database
  ↓
Start NEXUS
  ↓
Open dashboard
  ↓
Run or inspect a scenario
  ↓
Observe durable state and events
```
