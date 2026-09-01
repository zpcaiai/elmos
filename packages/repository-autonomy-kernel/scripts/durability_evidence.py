"""Crash-recovery evidence against a real PostgreSQL server.

Unit tests prove the logic; this proves the *durability*, which is a property of
the storage and the process boundary, not of the code.  The script deliberately
kills a child process mid-run — between announcing a side effect and observing
it — and then asks a fresh process, over a fresh connection, what the truth is.

Run:  ELMOS_KERNEL_PG_DSN=... python3 scripts/durability_evidence.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from elmos_autonomy_kernel.adapters.memory import SystemClock  # noqa: E402
from elmos_autonomy_kernel.adapters.postgres import (  # noqa: E402
    PostgresArtifactStore,
    PostgresEventStore,
    PostgresKeyValueStore,
    apply_migrations,
)
from elmos_autonomy_kernel.orchestrator import (  # noqa: E402
    DurableRun,
    RunState,
    StepDefinition,
    WorkflowDefinition,
    rollback_plan,
)

DSN = os.environ.get("ELMOS_KERNEL_PG_DSN", "")
STREAM = "evidence-crash-run"

WORKER = r'''
import os, sys
sys.path.insert(0, %(src)r)
import psycopg
from elmos_autonomy_kernel.adapters.memory import SystemClock
from elmos_autonomy_kernel.adapters.postgres import (
    PostgresArtifactStore, PostgresEventStore, PostgresKeyValueStore)
from elmos_autonomy_kernel.orchestrator import (
    Budget, DurableRun, RunState, StepDefinition, StepState, WorkflowDefinition)

connection = psycopg.connect(%(dsn)r, autocommit=True)
definition = WorkflowDefinition(
    workflow_id="wf-crash",
    workflow_version="2.0.0",
    task_spec_version="1",
    steps=(
        StepDefinition("plan", inputs_digest="d-plan"),
        StepDefinition("publish", requires=("plan",), inputs_digest="d-publish",
                       side_effecting=True, compensation="unpublish"),
    ),
)
run = DurableRun.create(
    run_id=%(stream)r, definition=definition,
    budget=Budget(limits={"usdMicros": 100000}, max_turns=20),
    events=PostgresEventStore(connection, SystemClock()),
    kv=PostgresKeyValueStore(connection),
    artifacts=PostgresArtifactStore(connection),
    clock=SystemClock(), fencing_token=1,
)
run.advance(RunState.SPECIFYING)
run.advance(RunState.PLANNING)
run.advance(RunState.EXECUTING)
run.start_step("plan")
run.mark_step("plan", StepState.SUCCEEDED, outputs_digest="out-plan")
run.start_step("publish")
key = run.begin_side_effect("publish")
print("INTENT_COMMITTED", key, flush=True)
# The process dies HERE, exactly where a real executor dies: the intent is
# durable, the observation was never written, and nobody marked the step.
os._exit(9)
'''


def _definition() -> WorkflowDefinition:
    """The same workflow the crashed worker declared.

    Recovery needs the definition; the log carries what *happened*, not what was
    supposed to happen.  Handing back a different definition is how a rehydrate
    quietly reinterprets history, so the two are written once here and shared.
    """

    return WorkflowDefinition(
        workflow_id="wf-crash",
        workflow_version="2.0.0",
        task_spec_version="1",
        steps=(
            StepDefinition("plan", inputs_digest="d-plan"),
            StepDefinition("publish", requires=("plan",), inputs_digest="d-publish",
                           side_effecting=True, compensation="unpublish"),
        ),
    )


def main() -> int:
    if not DSN:
        print("ELMOS_KERNEL_PG_DSN is not set", file=sys.stderr)
        return 2

    import psycopg

    setup = psycopg.connect(DSN, autocommit=False)
    apply_migrations(setup, str(ROOT / "sql" / "migrations"))
    with setup.cursor() as cursor:
        cursor.execute("DELETE FROM autonomy_kernel_event WHERE stream_id = %s", (STREAM,))
    setup.commit()
    setup.close()

    script = WORKER % {"src": str(ROOT / "src"), "dsn": DSN, "stream": STREAM}
    # S603: the argv is this file's own WORKER constant with paths this script
    # built; there is no external input on this line.  The child is spawned
    # precisely so it can die by os._exit(9) mid-transaction - that crash is
    # the evidence, and it cannot be produced in-process.
    child = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script], capture_output=True, text=True, check=False)
    crashed_as_expected = child.returncode == 9 and "INTENT_COMMITTED" in child.stdout

    # A brand-new process and a brand-new connection: nothing is inherited but
    # the database itself.
    connection = psycopg.connect(DSN, autocommit=True)
    store = PostgresEventStore(connection, SystemClock())
    definition = _definition()
    run = DurableRun.rehydrate(
        run_id=STREAM, definition=definition, events=store,
        kv=PostgresKeyValueStore(connection),
        artifacts=PostgresArtifactStore(connection),
        clock=SystemClock(), fencing_token=2,
    )
    view = run.view
    events = store.read(STREAM)

    unresolved = [
        intent.to_payload() for intent in view.intents.values() if intent.unresolved
    ]
    chain_ok = store.verify_chain(STREAM)
    plan = rollback_plan(view).to_payload()

    # Recovery must be idempotent: a keyed append delivered twice lands once,
    # and the second delivery gets the FIRST event back rather than a new one.
    # Measuring "no events were added" would be wrong — the first delivery is a
    # real append; what must not happen is a second.
    before = len(store.read(STREAM))
    replay_key = "recovery-probe-" + (
        unresolved[0]["idempotencyKey"][7:19] if unresolved else "none")
    first = store.append(STREAM, {"kind": "RECOVERY_PROBE", "key": replay_key},
                         idempotency_key=replay_key)
    second = store.append(STREAM, {"kind": "RECOVERY_PROBE", "key": replay_key},
                          idempotency_key=replay_key)
    after = len(store.read(STREAM))
    redelivery_deduped = (
        second.sequence == first.sequence
        and second.event_id == first.event_id
        and after - before == 1
    )

    with connection.cursor() as cursor:
        cursor.execute("SELECT version()")
        server = cursor.fetchone()[0]
    connection.close()

    report = {
        "generatedAt": datetime.now(tz=UTC).isoformat(),
        "server": server,
        "childExitCode": child.returncode,
        "crashedAtIntent": crashed_as_expected,
        "eventsDurableAfterCrash": len(events),
        "hashChainVerifies": chain_ok,
        "recoveredState": str(view.state),
        "recoveredStateIsNotSucceeded": view.state is not RunState.SUCCEEDED,
        "unresolvedSideEffects": unresolved,
        "rollbackPlanComplete": plan["complete"],
        "rollbackPlanUnresolved": plan["unresolved"],
        "keyedAppendsDelivered": 2,
        "eventsBeforeRedelivery": before,
        "eventsAfterRedelivery": after,
        "firstAppendSequence": first.sequence,
        "secondAppendSequence": second.sequence,
        "redeliveryDeduped": redelivery_deduped,
    }
    print(json.dumps(report, indent=2, default=str))

    ok = (
        crashed_as_expected
        and chain_ok
        and len(unresolved) == 1
        and report["recoveredStateIsNotSucceeded"]
        and redelivery_deduped
        and plan["complete"] is False
        and plan["unresolved"] == ["publish"]
    )
    # The verdict goes to stderr so that stdout is the evidence file and nothing
    # else: `python3 scripts/durability_evidence.py > evidence/...json` has to
    # produce a file that parses, or the evidence is not re-derivable from the
    # command that claims to produce it.
    print("\nDURABILITY_EVIDENCE:", "PASS" if ok else "FAIL", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
