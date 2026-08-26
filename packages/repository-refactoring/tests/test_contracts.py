"""Contract primitives: canonical encoding, digests, paths, validators."""

from __future__ import annotations

from decimal import Decimal

import pytest

from elmos_repository_refactoring.contracts import (
    ContractError,
    RiskClass,
    canonical_json,
    detect_newline,
    integer_value,
    match_path_glob,
    merge_digests,
    normalize_relative_path,
    parse_timestamp,
    path_within,
    reject_server_fields,
    reject_unknown_fields,
    require_digest,
    require_identifier,
    require_string_sequence,
    sha256_payload,
    sha256_text,
)


class TestCanonicalEncoding:
    def test_key_order_does_not_change_the_digest(self) -> None:
        left = {"b": 1, "a": {"d": 2, "c": 3}}
        right = {"a": {"c": 3, "d": 2}, "b": 1}
        assert sha256_payload(left) == sha256_payload(right)

    def test_list_order_does_change_the_digest(self) -> None:
        assert sha256_payload([1, 2]) != sha256_payload([2, 1])

    def test_integer_and_float_are_not_conflated_by_accident(self) -> None:
        assert canonical_json({"x": 1}) == '{"x":1}'
        assert canonical_json({"x": 1.5}) == '{"x":"1.5"}'

    def test_unicode_is_nfc_normalised(self) -> None:
        composed = "café"
        decomposed = "cafe\u0301"
        assert composed != decomposed
        assert sha256_payload({"k": composed}) == sha256_payload({"k": decomposed})

    def test_non_finite_numbers_are_refused(self) -> None:
        with pytest.raises(ContractError) as error:
            canonical_json({"x": float("inf")})
        assert error.value.code == "non_finite_number"

    def test_sets_are_refused_because_they_have_no_stable_order(self) -> None:
        with pytest.raises(ContractError) as error:
            canonical_json({"x": {1, 2}})
        assert error.value.code == "unencodable_value"

    def test_crlf_and_lf_hash_identically(self) -> None:
        assert sha256_text("a\r\nb") == sha256_text("a\nb")

    def test_merge_digests_is_order_independent(self) -> None:
        one = "sha256:" + "1" * 64
        two = "sha256:" + "2" * 64
        assert merge_digests([one, two]) == merge_digests([two, one])


class TestPaths:
    @pytest.mark.parametrize(
        "candidate",
        [
            "/etc/passwd",
            "../secrets",
            "a/../../b",
            "C:/windows",
            "a\\b",
            "nul.txt",
            "con",
            "trailing. /x",
        ],
    )
    def test_escapes_are_refused(self, candidate: str) -> None:
        with pytest.raises(ContractError):
            normalize_relative_path(candidate, "path")

    def test_normalisation_collapses_redundant_segments(self) -> None:
        assert normalize_relative_path("./a//b/./c", "path") == "a/b/c"

    def test_nul_byte_is_refused(self) -> None:
        with pytest.raises(ContractError):
            normalize_relative_path("a\x00b", "path")

    @pytest.mark.parametrize(
        ("path", "pattern", "expected"),
        [
            ("src/a/b.py", "src/**/*.py", True),
            ("src/b.py", "src/**/*.py", True),
            ("src/a/b.py", "src/*.py", False),
            ("src/a/b.py", "**/*.py", True),
            ("a/b/c", "a/**", True),
            # `**` spans zero or more segments, so `a/**` covers `a` itself and
            # `a/**/b` matches `a/b`.  Documented here because the alternative
            # reading (one-or-more) silently breaks directory-prefix rules.
            ("a", "a/**", True),
            ("a/b", "a/**/b", True),
            ("x.ts", "*.{ts,js}", False),
            ("x.ts", "*.ts", True),
            ("deep/x.spec.ts", "**/*.spec.ts", True),
        ],
    )
    def test_glob_does_not_cross_separators_with_single_star(
        self, path: str, pattern: str, expected: bool
    ) -> None:
        assert match_path_glob(path, pattern) is expected

    def test_trailing_slash_is_normalised_not_rejected(self) -> None:
        assert normalize_relative_path("a/b/", "path") == "a/b"

    def test_path_within_is_prefix_aware_not_substring_aware(self) -> None:
        assert path_within("src/a/b.py", "src/a")
        assert not path_within("src/ab/c.py", "src/a")


class TestValidators:
    def test_unknown_fields_are_reported_by_name(self) -> None:
        with pytest.raises(ContractError) as error:
            reject_unknown_fields({"a": 1, "zz": 2}, {"a"}, "obj")
        assert error.value.code == "unknown_field"
        assert error.value.details["unknown"] == ["zz"]

    def test_server_owned_fields_cannot_be_supplied(self) -> None:
        with pytest.raises(ContractError) as error:
            reject_server_fields({"digest": "x"}, {"digest"}, "obj")
        assert error.value.code == "server_field_forgery"

    def test_bool_is_not_an_integer(self) -> None:
        with pytest.raises(ContractError):
            integer_value(True, "n")

    def test_digest_shape_is_enforced(self) -> None:
        with pytest.raises(ContractError):
            require_digest("sha256:XYZ", "d")
        assert require_digest("sha256:" + "a" * 64, "d").startswith("sha256:")

    def test_duplicate_detection_in_string_sequences(self) -> None:
        with pytest.raises(ContractError) as error:
            require_string_sequence(["a", "a"], "seq", unique=True)
        assert error.value.code == "duplicate_entry"

    def test_identifier_rejects_spaces_and_slashes(self) -> None:
        assert require_identifier("run-1.2:3", "id") == "run-1.2:3"
        for bad in ("has space", "has/slash", ""):
            with pytest.raises(ContractError):
                require_identifier(bad, "id")

    def test_naive_timestamps_are_refused(self) -> None:
        with pytest.raises(ContractError) as error:
            parse_timestamp("2026-08-26T10:00:00", "t")
        assert error.value.code == "naive_timestamp"
        assert parse_timestamp("2026-08-26T10:00:00Z", "t").tzinfo is not None


class TestRiskClass:
    def test_max_of_picks_the_highest(self) -> None:
        assert RiskClass.max_of([RiskClass.R1, RiskClass.R4, RiskClass.R2]) is RiskClass.R4

    def test_empty_is_r0(self) -> None:
        assert RiskClass.max_of([]) is RiskClass.R0


def test_newline_detection_prefers_the_dominant_sequence() -> None:
    assert detect_newline("a\r\nb\r\nc\n") == "\r\n"
    assert detect_newline("a\nb\n") == "\n"
    assert detect_newline("plain") == "\n"


def test_decimal_round_trips_through_canonical_json() -> None:
    assert canonical_json({"v": Decimal("1.200")}) == '{"v":"1.2"}'
