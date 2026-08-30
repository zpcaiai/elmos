"""Supply-chain and repository-installation contract tests for the expansion ZIP.

The source archive is inert input. These tests inspect and rewrite ZIP bytes in
temporary directories; they never execute any bundled Python or shell file.
"""

from __future__ import annotations

from collections import Counter
import copy
import hashlib
import json
import shutil
import stat
import warnings
import zipfile
from pathlib import Path
from typing import Callable, Iterable

import pytest

from tooling import integrate_semantic_assurance_expansion_skills as integration


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = (
    REPOSITORY_ROOT
    / "skills/subskills/elmos-semantic-assurance-expansion-skills-v1.0.0.zip"
)
ARCHIVE_ROOT = "elmos-semantic-assurance-expansion-skills-v1.0.0"
EXPECTED_DIGEST = "0e470c927bf2840214d0e11d04ff0dbf914385b55c68c36370a5209e61994f60"
EXPECTED_BYTES = 632_740
EXPECTED_MEMBER_COUNT = 337
EXPECTED_FILE_COUNT = 194
EXPECTED_DIRECTORY_COUNT = 143
EXPECTED_UNCOMPRESSED_BYTES = 1_438_212
EXPECTED_INTERNAL_MANIFEST_COUNT = 192
INTERNAL_MANIFEST_EXCEPTIONS = frozenset(
    {
        "dist-manifests/package-file-manifest.json",
        "dist-manifests/validation.json",
    }
)
INSTALL_ROOTS = (Path(".agents/skills"), Path("agent-skills/runtime"))
ALIASES = {
    "elmos-proof-obligation-generator": (
        "elmos-semantic-assurance-proof-obligation-generator"
    ),
    "elmos-proof-cache-invalidation": (
        "elmos-semantic-assurance-proof-cache-invalidation"
    ),
}
OPERATIONS = frozenset(
    {
        "MODEL_NORMALIZATION",
        "SEMANTIC_COMPARISON",
        "GRAPH_ANALYSIS",
        "COVERAGE_ANALYSIS",
        "CORPUS_GOVERNANCE",
        "EVIDENCE_VALIDATION",
        "NATIVE_EXECUTION",
        "FORMAL_EXECUTION",
        "FUZZ_EXECUTION",
        "GATE_EVALUATION",
        "CACHE_INVALIDATION",
        "COUNTEREXAMPLE_REPLAY",
    }
)


@pytest.fixture(scope="module")
def audit() -> integration.ArchiveAudit:
    return integration.validate_archive(ARCHIVE)


@pytest.fixture(scope="module")
def expected(audit: integration.ArchiveAudit) -> integration.ExpectedRepository:
    return integration.build_expected(REPOSITORY_ROOT, audit)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _payload_bytes(value: object) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    raise AssertionError(f"unexpected expected-file payload: {type(value)!r}")


def _expected_files(expected: integration.ExpectedRepository) -> dict[Path, bytes]:
    files = getattr(expected, "files")
    normalized: dict[Path, bytes] = {}
    for path, payload in files.items():
        relative = Path(path)
        if relative.is_absolute():
            relative = relative.relative_to(REPOSITORY_ROOT)
        normalized[relative] = _payload_bytes(payload)
    return normalized


def _all_scalar_values(value: object) -> Iterable[object]:
    if isinstance(value, dict):
        for child in value.values():
            yield from _all_scalar_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _all_scalar_values(child)
    else:
        yield value


MemberMutation = Callable[[int, zipfile.ZipInfo, bytes], tuple[zipfile.ZipInfo, bytes]]


def _mutated_archive(
    destination: Path,
    mutation: MemberMutation,
    *,
    extra_member: tuple[zipfile.ZipInfo, bytes] | None = None,
) -> Path:
    """Rewrite the fixed archive without extracting or executing its content."""

    with (
        zipfile.ZipFile(ARCHIVE, "r") as source,
        zipfile.ZipFile(destination, "w") as target,
    ):
        target.comment = source.comment
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            for index, original in enumerate(source.infolist()):
                info = copy.copy(original)
                payload = b"" if original.is_dir() else source.read(original)
                info, payload = mutation(index, info, payload)
                target.writestr(info, payload)
            if extra_member is not None:
                target.writestr(*extra_member)
    return destination


def _validate_fixture(path: Path) -> integration.ArchiveAudit:
    data = path.read_bytes()
    return integration.validate_archive(
        path,
        expected_digest=_sha256(data),
        expected_bytes=len(data),
    )


def _materialize_expected(
    repository: Path,
    expected: integration.ExpectedRepository,
) -> None:
    """Create only the bounded repository surface needed by check_repository."""

    for relative, payload in _expected_files(expected).items():
        destination = repository / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)

    archive_copy = repository / "skills/subskills" / ARCHIVE.name
    archive_copy.parent.mkdir(parents=True, exist_ok=True)
    archive_copy.write_bytes(ARCHIVE.read_bytes())

    engine_source = REPOSITORY_ROOT / "engines/semantic-assurance-engine"
    if engine_source.is_dir():
        engine_target = repository / "engines/semantic-assurance-engine"
        if not engine_target.exists():
            shutil.copytree(engine_source, engine_target)

    # Conflicting source names remain owned by their original packages. They
    # are inputs to collision validation, not importer-owned output trees.
    for install_root in INSTALL_ROOTS:
        for source_name in ALIASES:
            source = REPOSITORY_ROOT / install_root / source_name
            target = repository / install_root / source_name
            if source.is_dir() and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source, target)


def test_archive_identity_member_limits_modes_and_compression(
    audit: integration.ArchiveAudit,
) -> None:
    data = ARCHIVE.read_bytes()
    assert len(data) == EXPECTED_BYTES
    assert _sha256(data) == EXPECTED_DIGEST

    with zipfile.ZipFile(ARCHIVE) as source:
        infos = source.infolist()
        files = [info for info in infos if not info.is_dir()]
        modes = Counter((info.external_attr >> 16) & 0xFFFF for info in infos)
        methods = Counter(info.compress_type for info in infos)

    assert len(infos) == EXPECTED_MEMBER_COUNT
    assert len(files) == EXPECTED_FILE_COUNT
    assert len(infos) - len(files) == EXPECTED_DIRECTORY_COUNT
    assert sum(info.file_size for info in files) == EXPECTED_UNCOMPRESSED_BYTES
    assert modes == Counter(
        {
            stat.S_IFDIR | 0o2755: 143,
            stat.S_IFREG | 0o644: 185,
            stat.S_IFREG | 0o755: 9,
        }
    )
    assert methods == Counter({zipfile.ZIP_STORED: 143, zipfile.ZIP_DEFLATED: 194})
    assert getattr(audit, "archive_sha256") == EXPECTED_DIGEST

    with pytest.raises(integration.IntegrationError, match="digest"):
        integration.validate_archive(ARCHIVE, expected_digest="0" * 64)


def test_internal_file_manifest_is_exact_and_two_exceptions_are_explicit(
    audit: integration.ArchiveAudit,
) -> None:
    del audit  # Validation must already have independently accepted the ZIP.
    prefix = f"{ARCHIVE_ROOT}/"
    with zipfile.ZipFile(ARCHIVE) as source:
        actual = {
            info.filename[len(prefix) :]: source.read(info)
            for info in source.infolist()
            if not info.is_dir()
        }
        internal = integration.strict_json_loads(
            actual["dist-manifests/package-file-manifest.json"],
            label="package-file-manifest.json",
        )

    records = internal["files"]
    assert internal["fileCount"] == EXPECTED_INTERNAL_MANIFEST_COUNT
    assert len(records) == EXPECTED_INTERNAL_MANIFEST_COUNT
    assert len({record["path"] for record in records}) == len(records)
    assert (
        set(actual) - {record["path"] for record in records}
        == INTERNAL_MANIFEST_EXCEPTIONS
    )
    for record in records:
        payload = actual[record["path"]]
        assert record["size"] == len(payload)
        assert record["sha256"] == _sha256(payload)


def test_duplicate_json_keys_fail_before_contract_interpretation(
    tmp_path: Path,
) -> None:
    with pytest.raises(integration.IntegrationError, match="duplicate JSON key"):
        integration.strict_json_loads(
            b'{"status":"pass","status":"not-run"}', label="attack"
        )

    manifest_member = f"{ARCHIVE_ROOT}/manifest.json"

    def duplicate_key(
        _index: int, info: zipfile.ZipInfo, payload: bytes
    ) -> tuple[zipfile.ZipInfo, bytes]:
        if info.filename == manifest_member:
            payload = payload.replace(
                b'"schema_version": "3.0",',
                b'"schema_version": "3.0",\n  "schema_version": "3.0",',
                1,
            )
        return info, payload

    attack = _mutated_archive(tmp_path / "duplicate-json-key.zip", duplicate_key)
    with pytest.raises(integration.IntegrationError):
        _validate_fixture(attack)


@pytest.mark.parametrize("attack", ["duplicate", "casefold", "traversal", "symlink"])
def test_malicious_zip_member_identity_fails_closed(
    attack: str,
    tmp_path: Path,
) -> None:
    with zipfile.ZipFile(ARCHIVE) as source:
        infos = source.infolist()
    file_indexes = [index for index, info in enumerate(infos) if not info.is_dir()]
    first, second = file_indexes[:2]
    first_name = infos[first].filename
    relative = first_name[len(f"{ARCHIVE_ROOT}/") :]

    def mutate(
        index: int, info: zipfile.ZipInfo, payload: bytes
    ) -> tuple[zipfile.ZipInfo, bytes]:
        if index != second:
            return info, payload
        if attack == "duplicate":
            info.filename = first_name
        elif attack == "casefold":
            info.filename = f"{ARCHIVE_ROOT}/{relative.swapcase()}"
        elif attack == "traversal":
            info.filename = f"{ARCHIVE_ROOT}/../escape"
        else:
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            payload = b"../../escape"
        return info, payload

    malicious = _mutated_archive(tmp_path / f"{attack}.zip", mutate)
    with pytest.raises(
        integration.IntegrationError,
        match="duplicate|collision|traversal|unsafe|symlink|special",
    ):
        _validate_fixture(malicious)


def test_member_count_mode_method_and_ratio_limits_fail_closed(
    tmp_path: Path,
) -> None:
    extra = zipfile.ZipInfo(f"{ARCHIVE_ROOT}/unexpected.txt")
    extra.create_system = 3
    extra.external_attr = (stat.S_IFREG | 0o644) << 16
    extra.compress_type = zipfile.ZIP_DEFLATED

    def unchanged(
        _index: int, info: zipfile.ZipInfo, payload: bytes
    ) -> tuple[zipfile.ZipInfo, bytes]:
        return info, payload

    too_many = _mutated_archive(
        tmp_path / "extra-member.zip",
        unchanged,
        extra_member=(extra, b"unexpected"),
    )
    with pytest.raises(integration.IntegrationError, match="member|count"):
        _validate_fixture(too_many)

    with zipfile.ZipFile(ARCHIVE) as source:
        regular = copy.copy(
            next(info for info in source.infolist() if not info.is_dir())
        )

    regular.external_attr = (stat.S_IFREG | 0o600) << 16
    with pytest.raises(integration.IntegrationError, match="mode|permission"):
        integration.validate_member(regular)

    regular.external_attr = (stat.S_IFREG | 0o644) << 16
    regular.compress_type = zipfile.ZIP_BZIP2
    with pytest.raises(integration.IntegrationError, match="compression|method"):
        integration.validate_member(regular)

    regular.compress_type = zipfile.ZIP_DEFLATED
    regular.file_size = 200_000
    regular.compress_size = 1
    with pytest.raises(integration.IntegrationError, match="ratio|compression"):
        integration.validate_member(regular)


def test_expected_installation_is_repo_owned_dual_root_and_collision_safe(
    audit: integration.ArchiveAudit,
    expected: integration.ExpectedRepository,
) -> None:
    files = _expected_files(expected)
    manifest = getattr(audit, "manifest")
    source_skills = {skill["name"]: skill for skill in manifest["skills"]}
    installed_names = {
        ALIASES.get(source_name, source_name) for source_name in source_skills
    }
    assert len(installed_names) == 132
    assert len(source_skills) - len(ALIASES) == 130

    with zipfile.ZipFile(ARCHIVE) as source:
        source_docs = {
            skill["name"]: source.read(f"{ARCHIVE_ROOT}/{skill['path']}")
            for skill in manifest["skills"]
        }

    observed_operations: set[str] = set()
    for install_root in INSTALL_ROOTS:
        observed = {
            path.relative_to(install_root).parts[0]
            for path in files
            if path.is_relative_to(install_root) and path.name == "SKILL.md"
        }
        assert observed == installed_names

        for source_name, skill in source_skills.items():
            installed_name = ALIASES.get(source_name, source_name)
            wrapper_path = install_root / installed_name / "SKILL.md"
            contract_path = install_root / installed_name / "compiled-contract.json"
            interface_path = install_root / installed_name / "agents/openai.yaml"
            assert wrapper_path in files
            assert contract_path in files
            assert interface_path in files
            assert files[wrapper_path] != source_docs[source_name]

            contract = json.loads(files[contract_path])
            scalar_values = set(_all_scalar_values(contract))
            assert source_name in scalar_values
            assert skill["id"] in scalar_values
            assert (
                EXPECTED_DIGEST in scalar_values
                or f"sha256:{EXPECTED_DIGEST}" in scalar_values
            )
            assert "NOT_RUN" in scalar_values
            assert "NOT_CERTIFIED" in scalar_values
            observed_operations.update(
                value for value in scalar_values if value in OPERATIONS
            )

    assert observed_operations == OPERATIONS
    deletions = {Path(path) for path in getattr(expected, "deletions", ())}
    for source_name, alias in ALIASES.items():
        for install_root in INSTALL_ROOTS:
            original_root = install_root / source_name
            assert not any(
                path == original_root or original_root in path.parents
                for path in deletions
            )
            for original in (REPOSITORY_ROOT / original_root).rglob("*"):
                if not original.is_file():
                    continue
                relative = original.relative_to(REPOSITORY_ROOT)
                if relative in files:
                    assert files[relative] == original.read_bytes()
            assert install_root / alias / "compiled-contract.json" in files

    proof_owner = (
        REPOSITORY_ROOT / ".agents/skills/elmos-proof-obligation-generator/SKILL.md"
    ).read_text(encoding="utf-8")
    assert "pack: 09-evaluation-proof-certification" in proof_owner
    assert "version: 3.0.0" in proof_owner
    cache_owner = (
        REPOSITORY_ROOT / ".agents/skills/elmos-proof-cache-invalidation/SKILL.md"
    ).read_text(encoding="utf-8")
    assert 'source_package: "elmos-formal-assurance-kernel-v1.0.0"' in cache_owner
    assert (
        'source_sha256: "sha256:eaeaf12228ba4dcd58d3be407aa25bed275c3fa4f2c58defda34a88f9d701b44"'
        in cache_owner
    )

    for installed_name in installed_names:
        for relative in (
            Path("SKILL.md"),
            Path("agents/openai.yaml"),
            Path("compiled-contract.json"),
        ):
            left = files[INSTALL_ROOTS[0] / installed_name / relative]
            right = files[INSTALL_ROOTS[1] / installed_name / relative]
            assert left == right


def test_source_assurance_and_receipt_never_promote_missing_evidence(
    expected: integration.ExpectedRepository,
) -> None:
    files = _expected_files(expected)
    receipts = [
        payload
        for path, payload in files.items()
        if path.name in {"QUALIFICATION_RECEIPT.json", "qualification-receipt.json"}
    ]
    assert len(receipts) == 1
    receipt = json.loads(receipts[0])
    scalars = set(_all_scalar_values(receipt))
    assert EXPECTED_DIGEST in scalars or f"sha256:{EXPECTED_DIGEST}" in scalars
    assert "NOT_RUN" in scalars
    assert "NOT_CERTIFIED" in scalars
    assert not any(
        value is True for key, value in receipt.items() if "certif" in key.lower()
    )

    serialized = json.dumps(receipt, sort_keys=True).lower()
    normalized = serialized.replace("_", "").replace("-", "")
    assert '"signaturepresent": false' in normalized
    assert '"sbompresent": false' in normalized
    assert '"provenanceattestationpresent": false' in normalized
    assert "byteidentityonly" in normalized


@pytest.mark.parametrize("tamper_kind", ["compiled-contract", "receipt"])
def test_check_repository_fails_on_digest_bound_drift(
    tamper_kind: str,
    tmp_path: Path,
    audit: integration.ArchiveAudit,
    expected: integration.ExpectedRepository,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _materialize_expected(repository, expected)

    clean = integration.check_repository(repository, audit)
    assert clean.ok, getattr(clean, "errors", clean)

    files = _expected_files(expected)
    if tamper_kind == "compiled-contract":
        relative = next(path for path in files if path.name == "compiled-contract.json")
    else:
        relative = next(
            path
            for path in files
            if path.name in {"QUALIFICATION_RECEIPT.json", "qualification-receipt.json"}
        )
    target = repository / relative
    target.write_bytes(target.read_bytes() + b"\n")

    report = integration.check_repository(repository, audit)
    assert not report.ok
    errors = " ".join(getattr(report, "errors", ())).lower()
    assert any(token in errors for token in ("drift", "digest", "tamper", "mismatch"))


def test_cli_check_propagates_drift_as_nonzero(
    audit: integration.ArchiveAudit,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    drift = integration.CheckReport(
        ok=False,
        errors=("drift/tamper: compiled contract digest mismatch",),
        blockers=audit.blockers,
        checked_file_count=1,
    )
    monkeypatch.setattr(
        integration, "validate_archive", lambda *_args, **_kwargs: audit
    )
    monkeypatch.setattr(
        integration, "check_repository", lambda *_args, **_kwargs: drift
    )

    exit_code = integration.main(
        [
            "--repository-root",
            str(REPOSITORY_ROOT),
            "--archive",
            str(ARCHIVE),
            "--check",
        ]
    )
    assert exit_code == 1
    assert "drift_or_tamper" in capsys.readouterr().err.lower()
