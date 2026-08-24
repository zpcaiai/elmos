"""The API contract, exercised over real HTTP.

These assertions are the ones an OpenAPI document cannot make on its own: that a
client which disconnects and reconnects with Last-Event-ID is served exactly what
it missed, and that a replayed submission creates nothing new.
"""
import json
import urllib.error
import urllib.request

import pytest
from conftest import PROJECT_PATH, TASKS_PATH

from elmos_execution_intelligence.durable import DurableStore, LogicalClock
from elmos_execution_intelligence.io_utils import load_json
from elmos_execution_intelligence.server import ReferenceServer

PROJECT = load_json(PROJECT_PATH)
TASKS = load_json(TASKS_PATH)


def _small_dag(n=3):
    return {
        "schema_version": "1.0.0",
        "dag_id": "http-dag",
        "tasks": [
            {
                "id": f"h{i}", "name": f"task {i}",
                "depends_on": [f"h{i - 1}"] if i else [],
                "category": "verification", "complexity": "medium",
                "system": {"optimistic_minutes": 1, "most_likely_minutes": 2,
                           "pessimistic_minutes": 4, "worker_units": 1,
                           "token_profile": {"input": 100, "output": 50}},
                "human": {"hours_by_role": {"qa": 1}},
            }
            for i in range(n)
        ],
    }


@pytest.fixture()
def server():
    store = DurableStore(":memory:", clock=LogicalClock(start=1000.0, step=1.0),
                         allow_cross_thread=True)
    running = ReferenceServer(store, port=0).start()
    yield running, store
    running.stop()
    store.close()


def _request(url, method="GET", body=None, headers=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    assert url.startswith("http://127.0.0.1:"), url  # S310: the only scheme this helper opens
    request = urllib.request.Request(url, data=data, method=method)  # noqa: S310 - asserted above
    request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 - asserted above
            return response.status, response.headers, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read().decode("utf-8")


def _create(base, key="key-1", dag=None):
    return _request(f"{base}/runs", "POST",
                    {"projectProfile": PROJECT, "taskDag": dag or _small_dag()},
                    {"Idempotency-Key": key})


def test_a_run_is_created_and_reported(server):
    running, _ = server
    status, _, body = _create(running.base_url)
    assert status == 201
    run = json.loads(body)
    assert run["state"] == "succeeded"
    assert run["lastEventSeq"] > 0

    status, _, body = _request(f"{running.base_url}/runs/{run['runId']}")
    assert status == 200
    detail = json.loads(body)
    assert len(detail["tasks"]) == 3
    assert detail["eta"]["excludes"]


def test_a_state_changing_request_without_an_idempotency_key_is_blocked(server):
    running, _ = server
    status, _, body = _request(f"{running.base_url}/runs", "POST",
                               {"projectProfile": PROJECT, "taskDag": _small_dag()})
    assert status == 422
    problem = json.loads(body)
    assert problem["missing"] == ["Idempotency-Key"]


def test_a_replayed_submission_creates_nothing_new(server):
    running, store = server
    first_status, _, first_body = _create(running.base_url, key="same")
    second_status, _, second_body = _create(running.base_url, key="same")

    assert first_status == 201
    assert second_status == 200, "a replay is not a creation"
    assert json.loads(first_body)["runId"] == json.loads(second_body)["runId"]
    assert len(store.connection.execute("SELECT run_id FROM run").fetchall()) == 1


def test_the_same_key_with_a_different_body_is_a_conflict(server):
    running, _ = server
    _create(running.base_url, key="k")
    status, _, body = _create(running.base_url, key="k", dag=_small_dag(2))
    assert status == 409
    assert "different request body" in json.loads(body)["detail"]


def test_missing_required_fields_are_named(server):
    running, _ = server
    status, _, body = _request(f"{running.base_url}/runs", "POST", {},
                               {"Idempotency-Key": "x"})
    assert status == 422
    assert set(json.loads(body)["missing"]) == {"projectProfile", "taskDag"}


def test_polling_replays_exactly_what_was_missed(server):
    running, _ = server
    run_id = json.loads(_create(running.base_url)[2])["runId"]

    _, _, body = _request(f"{running.base_url}/runs/{run_id}/events?afterSeq=0")
    everything = json.loads(body)["events"]
    cut = len(everything) // 2
    last_seen = everything[cut - 1]["seq"]

    _, _, body = _request(f"{running.base_url}/runs/{run_id}/events?afterSeq={last_seen}")
    replayed = json.loads(body)["events"]
    assert [e["seq"] for e in replayed] == [e["seq"] for e in everything[cut:]]
    assert all(e["seq"] > last_seen for e in replayed)


def test_last_event_id_header_drives_the_sse_replay(server):
    running, _ = server
    run_id = json.loads(_create(running.base_url)[2])["runId"]

    status, headers, body = _request(
        f"{running.base_url}/runs/{run_id}/events", headers={
            "Accept": "text/event-stream", "Last-Event-ID": "3"})
    assert status == 200
    assert headers["Content-Type"].startswith("text/event-stream")
    ids = [int(line.split(": ", 1)[1]) for line in body.splitlines() if line.startswith("id: ")]
    assert ids, body
    assert min(ids) == 4, "replay starts immediately after the last seen sequence"
    assert ids == sorted(ids)
    assert ids == list(range(ids[0], ids[0] + len(ids))), "no gaps"


def test_sse_and_polling_return_the_same_rows(server):
    running, _ = server
    run_id = json.loads(_create(running.base_url)[2])["runId"]

    _, _, polled = _request(f"{running.base_url}/runs/{run_id}/events?afterSeq=5")
    polled_ids = [e["seq"] for e in json.loads(polled)["events"]]

    _, _, streamed = _request(f"{running.base_url}/runs/{run_id}/events",
                              headers={"Accept": "text/event-stream", "Last-Event-ID": "5"})
    streamed_ids = [int(line.split(": ", 1)[1]) for line in streamed.splitlines()
                    if line.startswith("id: ")]
    assert polled_ids == streamed_ids


def test_a_malformed_last_event_id_is_rejected(server):
    running, _ = server
    run_id = json.loads(_create(running.base_url)[2])["runId"]
    status, _, _ = _request(f"{running.base_url}/runs/{run_id}/events",
                            headers={"Last-Event-ID": "not-a-number"})
    assert status == 400


def test_an_unknown_run_is_a_problem_document(server):
    running, _ = server
    status, headers, body = _request(f"{running.base_url}/runs/00000000-0000-4000-8000-000000000000")
    assert status == 404
    assert headers["Content-Type"].startswith("application/problem+json")
    assert json.loads(body)["status"] == 404


def test_artifacts_and_checkpoints_are_served(server):
    running, _ = server
    run_id = json.loads(_create(running.base_url)[2])["runId"]

    _, _, body = _request(f"{running.base_url}/runs/{run_id}/artifacts")
    manifest = json.loads(body)
    assert manifest["sealed"] is True
    assert len(manifest["artifacts"]) == 3
    assert all(len(a["sha256"]) == 64 for a in manifest["artifacts"])

    _, _, body = _request(f"{running.base_url}/runs/{run_id}/checkpoints")
    assert len(json.loads(body)["checkpoints"]) == 3


def test_cancel_is_idempotent(server):
    running, _ = server
    run_id = json.loads(_create(running.base_url)[2])["runId"]
    first = _request(f"{running.base_url}/runs/{run_id}/cancel", "POST", {},
                     {"Idempotency-Key": "c1"})
    second = _request(f"{running.base_url}/runs/{run_id}/cancel", "POST", {},
                      {"Idempotency-Key": "c1"})
    assert first[0] == 202 and second[0] == 202
    assert json.loads(first[2])["runId"] == json.loads(second[2])["runId"]


def test_a_bearer_token_is_enforced_when_configured():
    store = DurableStore(":memory:", clock=LogicalClock(), allow_cross_thread=True)
    running = ReferenceServer(store, port=0, bearer="secret").start()
    try:
        status, _, _ = _request(f"{running.base_url}/runs")
        assert status == 401
        status, _, _ = _request(f"{running.base_url}/runs",
                                headers={"Authorization": "Bearer secret"})
        assert status == 200
    finally:
        running.stop()
        store.close()


def test_the_server_refuses_a_thread_bound_store():
    store = DurableStore(":memory:", clock=LogicalClock())
    with pytest.raises(ValueError, match="allow_cross_thread"):
        ReferenceServer(store, port=0)
    store.close()
