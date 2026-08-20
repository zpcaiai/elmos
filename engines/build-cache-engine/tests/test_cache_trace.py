"""Traces you can keep, and corpora you can trust.

Two failure modes matter here and neither is about cache performance. The first
is a trace that carries something it should not -- a path, a prompt, a tenant
name -- because such a corpus can never be shared, and an unshareable corpus
means every policy claim stays unverifiable. The second is a corpus whose
splits overlap or leak, because then a tuned policy evaluates itself on its own
training data and the number that comes out is meaningless.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from elmos_build_cache.cache_trace import (
    GENERATORS,
    Access,
    CacheTraceEvent,
    Split,
    Tier,
    TraceCorpus,
    TraceRecorder,
    assert_privacy,
    default_splits,
    detect_drift,
    detect_leakage,
    key_hash,
    sufficient_sample,
    workload_features,
)
from elmos_build_cache.errors import ContractViolation

DIGEST = "sha256:" + "a" * 64


def event(**kwargs: object) -> CacheTraceEvent:
    base = {
        "event_id": "evt-1",
        "timestamp_bucket": 0,
        "tier": Tier.L1_LOCAL_CAS.value,
        "key_hash": DIGEST,
        "namespace_hash": "sha256:" + "b" * 64,
        "size_bytes": 1000,
        "access": Access.GET.value,
        "stage_class": "ir",
        "recompute_ms": 10.0,
        "restore_ms": 1.0,
    }
    base.update(kwargs)
    return CacheTraceEvent(**base)  # type: ignore[arg-type]


# ==========================================================================
# the event
# ==========================================================================
def test_an_event_requires_digests_not_identifiers() -> None:
    with pytest.raises(ContractViolation, match="key_hash"):
        event(key_hash="src/main/java/App.java")
    with pytest.raises(ContractViolation, match="namespace_hash"):
        event(namespace_hash="acme-corp")


def test_an_event_rejects_an_unknown_tier_or_access() -> None:
    with pytest.raises(ValueError):
        event(tier="L9_TAPE")
    with pytest.raises(ValueError):
        event(access="DELETE")


def test_an_event_round_trips_through_json() -> None:
    original = event(model_tokens=12, next_use_distance=4, hit=True)
    restored = CacheTraceEvent.from_dict(json.loads(json.dumps(original.to_dict())))
    assert restored == original


def test_unknown_fields_are_refused_rather_than_ignored() -> None:
    payload = event().to_dict()
    payload["source_path"] = "/home/dev/App.java"
    with pytest.raises(ContractViolation, match="unknown trace fields"):
        CacheTraceEvent.from_dict(payload)


# ==========================================================================
# capture
# ==========================================================================
def test_the_tenant_pseudonym_is_an_hmac_not_a_hash() -> None:
    """A bare digest of a tenant name is reversible by anyone with a name list."""
    from hashlib import sha256

    recorder = TraceRecorder(b"capture-secret")
    pseudonym = recorder.namespace_hash("acme-corp")
    plain = "sha256:" + sha256(b"acme-corp").hexdigest()
    assert pseudonym != plain, "the pseudonym is a plain digest and can be brute-forced"

    other = TraceRecorder(b"another-secret")
    assert other.namespace_hash("acme-corp") != pseudonym, "the secret does not vary the pseudonym"
    assert recorder.namespace_hash("acme-corp") == pseudonym, "the pseudonym is not stable"


def test_sampling_is_deterministic_in_the_key_so_reuse_chains_survive() -> None:
    """Random sampling would shred reuse distances into noise."""
    recorder = TraceRecorder(b"secret", sample_rate=0.5)
    keys = [key_hash(f"object-{index}") for index in range(200)]
    first = {key for key in keys if recorder._sampled(key)}  # noqa: SLF001 - the property under test
    second = {key for key in keys if recorder._sampled(key)}  # noqa: SLF001
    assert first == second
    assert 0 < len(first) < len(keys)


def test_a_tenant_budget_stops_one_tenant_filling_the_corpus() -> None:
    recorder = TraceRecorder(b"secret", per_tenant_budget=5)
    for index in range(20):
        recorder.record(
            key_hash=key_hash(f"k{index}"),
            tenant_id="loud",
            tier=Tier.L1_LOCAL_CAS,
            access=Access.GET,
            size_bytes=100,
            stage_class="ir",
            recompute_ms=1.0,
            restore_ms=0.1,
        )
    assert recorder.stats()["captured"] == 5
    assert recorder.stats()["dropped_by_budget"] == 15


def test_capture_produces_events_that_pass_the_privacy_rule() -> None:
    recorder = TraceRecorder(b"secret")
    recorder.record(
        key_hash=key_hash("some/very/private/path.java"),
        tenant_id="acme",
        tier=Tier.L2_REMOTE_CAS,
        access=Access.PUT,
        size_bytes=4096,
        stage_class="generation",
        recompute_ms=8000.0,
        restore_ms=4.0,
    )
    assert_privacy(recorder.events)


# ==========================================================================
# the privacy rule itself
# ==========================================================================
def test_privacy_refuses_a_path_smuggled_into_the_stage_class() -> None:
    with pytest.raises(ContractViolation, match="short identifier"):
        assert_privacy([event(stage_class="src/main/java/App.java")])


def test_privacy_refuses_free_text_in_a_closed_vocabulary_field() -> None:
    with pytest.raises(ContractViolation, match="closed vocabulary"):
        assert_privacy([event(validation_level="probably fine")])


def test_privacy_refuses_a_quoted_prompt_fragment() -> None:
    with pytest.raises(ContractViolation):
        assert_privacy([event(stage_class='say "hello"')])


# ==========================================================================
# corpora
# ==========================================================================
def test_splits_are_time_separated_by_construction() -> None:
    bounds = default_splits(1000)
    ordered = sorted(bounds.values())
    for index in range(len(ordered) - 1):
        assert ordered[index + 1][0] >= ordered[index][1]
    assert bounds[Split.TEST.value][1] == 1000


def test_overlapping_splits_are_refused() -> None:
    events = tuple(event(event_id=f"e{index}", key_hash=key_hash(f"k{index}")) for index in range(20))
    with pytest.raises(ContractViolation, match="overlap"):
        TraceCorpus(events, splits={"train": (0, 15), "test": (10, 20)})


def test_a_corpus_digests_itself_and_every_split() -> None:
    corpus = GENERATORS["identical-rerun"]()
    manifest = corpus.manifest()
    assert manifest["corpus_digest"].startswith("sha256:")
    assert set(manifest["split_digests"]) == set(corpus.splits)
    assert manifest["events"] == len(corpus.events)
    # The digest is over content: a different corpus has a different digest.
    assert GENERATORS["monorepo-scan"]().digest() != corpus.digest()


def test_a_corpus_round_trips_through_jsonl(tmp_path: Path) -> None:
    corpus = GENERATORS["single-file-edit"]()
    path = corpus.write_jsonl(tmp_path / "trace.jsonl")
    restored = TraceCorpus.read_jsonl(path, label=corpus.label)
    assert restored.digest() == corpus.digest()


def test_leakage_detection_catches_a_test_window_before_the_train_window() -> None:
    events = tuple(event(event_id=f"e{index}", key_hash=key_hash(f"k{index}")) for index in range(40))
    corpus = TraceCorpus(events, splits={"test": (0, 10), "train": (10, 40)})
    findings = detect_leakage(corpus)
    assert any(finding.kind == "TEST_BEFORE_TRAIN" for finding in findings)


def test_leakage_detection_catches_a_negative_next_use() -> None:
    events = tuple(
        event(event_id=f"e{index}", key_hash=key_hash(f"k{index}"), next_use_distance=-1)
        for index in range(12)
    )
    corpus = TraceCorpus(events, splits={"test": (0, 12)})
    assert any(finding.kind == "NEGATIVE_NEXT_USE" for finding in detect_leakage(corpus))


def test_a_generated_corpus_has_no_leakage() -> None:
    for name, generator in GENERATORS.items():
        assert detect_leakage(generator()) == (), name


# ==========================================================================
# fingerprints, drift, sample size
# ==========================================================================
def test_the_fingerprint_separates_the_workloads_it_is_meant_to() -> None:
    scan = workload_features(GENERATORS["monorepo-scan"]().events)
    rerun = workload_features(GENERATORS["identical-rerun"]().events)
    binaries = workload_features(GENERATORS["large-binaries"]().events)

    assert scan["one_hit_ratio"] > rerun["one_hit_ratio"]
    assert rerun["reuse_ratio"] > scan["reuse_ratio"]
    assert binaries["size_cv"] > rerun["size_cv"]


def test_the_fingerprint_records_known_future_separately_from_prediction() -> None:
    planned = workload_features(GENERATORS["dag-known-future"]().events)
    unplanned = workload_features(GENERATORS["identical-rerun"]().events)
    assert planned["known_future_ratio"] >= 0.4
    assert unplanned["known_future_ratio"] == 0.0


def test_drift_between_two_different_workloads_is_reported() -> None:
    drift = detect_drift(
        GENERATORS["identical-rerun"]().events, GENERATORS["monorepo-scan"]().events
    )
    assert drift["drifted"] is True
    assert "one_hit_ratio" in drift["drifted_features"]


def test_no_drift_between_a_corpus_and_itself() -> None:
    events = GENERATORS["identical-rerun"]().events
    assert detect_drift(events, events)["drifted"] is False


def test_a_short_window_is_refused_for_certification() -> None:
    events = GENERATORS["identical-rerun"]().events
    enough, detail = sufficient_sample(events[:20])
    assert enough is False and "below" in detail
    assert sufficient_sample(events)[0] is True


@pytest.mark.parametrize("name", sorted(GENERATORS))
def test_every_generator_produces_a_usable_corpus(name: str) -> None:
    corpus = GENERATORS[name]()
    assert corpus.events
    assert_privacy(corpus.events)
    assert corpus.manifest()["features"]["request_count"] == len(corpus.events)
