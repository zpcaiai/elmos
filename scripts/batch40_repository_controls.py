#!/usr/bin/env python3
"""Exercise bounded repository-owned controls for the Batch 40 pack.

The report produced here proves only local control-plane behavior. Scanner
providers, active DAST/IAST, isolated builders, production signatures,
independent assessment, approval, and certification remain NOT_RUN.

Exit codes:
  0: all repository-owned controls passed
  2: requested scope or input is invalid
  3: one or more repository-owned controls failed closed
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


CAPABILITIES = (
    "b40-ai-model-supply-chain",
    "b40-artifact-container-signing",
    "b40-container-kubernetes-iac-scanning",
    "b40-dast-iast-integration",
    "b40-independent-security-assessment",
    "b40-isolated-trusted-builder",
    "b40-psirt-security-incident",
    "b40-sast-integration",
    "b40-secure-code-review-approval",
    "b40-slsa-provenance",
    "b40-vex-applicability",
)
EXTERNAL_KEYS = (
    "sast",
    "dastIast",
    "containerIac",
    "artifactSigning",
    "isolatedBuilder",
    "independentAssessment",
)
PSIRT_STATES = (
    "RECEIVED",
    "TRIAGED",
    "CONTAINED",
    "REMEDIATED",
    "VERIFIED",
    "DISCLOSED",
    "CLOSED",
)
SOURCE_SUFFIXES = (".cs", ".go", ".java", ".js", ".kt", ".py", ".rs", ".ts", ".tsx")
IAC_SUFFIXES = (".tf", ".tfvars")


class ControlError(ValueError):
    """Raised when the requested repository scope cannot be evaluated."""


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def git_revision(repo: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    revision = result.stdout.strip()
    if result.returncode or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ControlError("repository HEAD is not an exact Git revision")
    return revision


def tracked_files(repo: Path, patterns: Iterable[str]) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "--", *patterns],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise ControlError(f"tracked-file inventory failed: {result.stderr.strip()}")
    return sorted({line for line in result.stdout.splitlines() if line})


def load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ControlError(f"{label} is unreadable: {exc}") from exc
    if not isinstance(value, dict):
        raise ControlError(f"{label} must be a JSON object")
    return value


def load_array(path: Path, label: str) -> list[Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ControlError(f"{label} is unreadable: {exc}") from exc
    if not isinstance(value, list):
        raise ControlError(f"{label} must be a JSON array")
    return value


def validate_config(config: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if config.get("schemaVersion") != 1:
        failures.append("schemaVersion must equal 1")
    if not isinstance(config.get("policyId"), str) or not config["policyId"]:
        failures.append("policyId is required")
    if not isinstance(config.get("owner"), str) or not config["owner"]:
        failures.append("owner is required")
    if config.get("capabilities") != list(CAPABILITIES):
        failures.append("capabilities must contain the exact ordered Batch 40 repository capability set")
    if set(config.get("requiredAdapters", [])) != {
        "SAST", "SCA", "IAC", "CONTAINER", "DAST", "SBOM", "PROVENANCE", "VEX"
    }:
        failures.append("requiredAdapters must contain the exact Batch 40 adapter set")
    external = config.get("externalExecution")
    if not isinstance(external, dict) or set(external) != set(EXTERNAL_KEYS):
        failures.append("externalExecution must contain the exact external operation set")
    elif any(external.get(key) != "NOT_RUN" for key in EXTERNAL_KEYS):
        failures.append("repository controls cannot promote an external operation beyond NOT_RUN")
    return failures


def validate_codeowners(path: Path, required_patterns: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    failures: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [f"CODEOWNERS is unreadable: {exc}"], {}
    records: dict[str, list[str]] = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) < 2:
            failures.append(f"CODEOWNERS entry has no owner: {line}")
            continue
        owners = fields[1:]
        if not all(owner.startswith("@") and len(owner) > 1 for owner in owners):
            failures.append(f"CODEOWNERS entry has an invalid owner: {line}")
        records[fields[0]] = owners
    for pattern in required_patterns:
        if pattern not in records:
            failures.append(f"sensitive path has no exact CODEOWNERS rule: {pattern}")
    return failures, records


def validate_psirt(policy: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if policy.get("schemaVersion") != 1 or not policy.get("policyId") or not policy.get("owner"):
        failures.append("PSIRT schemaVersion, policyId, and owner are required")
    channel = policy.get("privateReportingChannel")
    if not isinstance(channel, str) or not channel.startswith("github-security-advisory://"):
        failures.append("PSIRT must declare a private GitHub Security Advisory channel")
    if policy.get("states") != list(PSIRT_STATES):
        failures.append("PSIRT lifecycle must preserve the exact ordered states")
    slas = policy.get("severitySlaHours")
    if not isinstance(slas, dict) or set(slas) != {"critical", "high", "medium", "low"}:
        failures.append("PSIRT must define an SLA for every supported severity")
    elif any(not isinstance(value, int) or isinstance(value, bool) or value <= 0 for value in slas.values()):
        failures.append("every PSIRT SLA must be a positive integer hour count")
    required_fields = policy.get("requiredCaseFields")
    if not isinstance(required_fields, list) or not {
        "caseId", "receivedAt", "severity", "owner", "affectedArtifacts", "evidenceRefs", "currentState"
    }.issubset(required_fields):
        failures.append("PSIRT case requirements are incomplete")
    if not isinstance(policy.get("closureRequirements"), list) or len(policy["closureRequirements"]) < 5:
        failures.append("PSIRT closure requirements are incomplete")
    if policy.get("automaticRiskAcceptance") is not False or policy.get("automaticCaseClosure") is not False:
        failures.append("PSIRT automatic risk acceptance and case closure must be disabled")
    if policy.get("externalExerciseStatus") != "NOT_RUN" or policy.get("independentVerification") != "NOT_RUN":
        failures.append("PSIRT external exercise and independent verification must remain NOT_RUN")
    return failures


def validate_license_policy(policy: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if policy.get("schemaVersion") != 1 or not policy.get("policyId") or not policy.get("owner"):
        failures.append("license review schemaVersion, policyId, and owner are required")
    if policy.get("status") != "DRAFT_NOT_APPROVED":
        failures.append("an unapproved repository policy must remain DRAFT_NOT_APPROVED")
    if policy.get("defaultDecision") != "BLOCK_PENDING_REVIEW":
        failures.append("unknown license decisions must block pending review")
    for field in ("allowedLicenses", "prohibitedLicenses", "contextDependentLicenses"):
        if policy.get(field) != []:
            failures.append(f"{field} must remain empty until an accountable policy is approved")
    if policy.get("decisionStatuses") != [
        "PENDING_METADATA", "PENDING_APPROVAL", "APPROVED", "PROHIBITED", "CONTEXT_REVIEW_REQUIRED"
    ]:
        failures.append("license decision lifecycle is incomplete")
    requirements = policy.get("approvalRequirements")
    if not isinstance(requirements, dict) or not requirements or not all(value is True for value in requirements.values()):
        failures.append("every license approval requirement must be mandatory")
    if policy.get("automaticApproval") is not False:
        failures.append("automatic license approval must be disabled")
    if policy.get("independentVerification") != "NOT_RUN":
        failures.append("license policy independent verification must remain NOT_RUN")
    return failures


def build_license_review_queue(inventory: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    failures: list[str] = []
    components = inventory.get("components")
    if not isinstance(components, list):
        return ["dependency inventory components must be a list"], []
    external = [item for item in components if isinstance(item, dict) and not item.get("internal")]
    queue: list[dict[str, Any]] = []
    seen: set[str] = set()
    for component in external:
        purl = component.get("purl")
        if not isinstance(purl, str) or not purl or purl in seen:
            failures.append("external component identities must have unique purls")
            continue
        seen.add(purl)
        observed = component.get("licenses")
        if not observed and component.get("license"):
            observed = [component["license"]]
        if not isinstance(observed, list):
            observed = []
        queue.append({
            "componentRef": purl,
            "ecosystem": component.get("ecosystem"),
            "version": component.get("version"),
            "declaredIn": component.get("declaredIn", []),
            "observedLicenseMetadata": observed,
            "decisionStatus": "PENDING_APPROVAL" if observed else "PENDING_METADATA",
            "approvalRef": None,
            "approver": None,
            "reviewTrigger": "approved license policy or component/use-case change",
        })
    expected = inventory.get("totals", {}).get("externalComponentCount")
    if expected != len(queue):
        failures.append(f"license review queue has {len(queue)} records but inventory declares {expected}")
    if any(item["decisionStatus"] == "APPROVED" for item in queue):
        failures.append("the draft queue must not manufacture approved license decisions")
    return failures, queue


def validate_adapter_policies(adapter: dict[str, Any], profile: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    failures: list[str] = []
    required = {"SAST", "SCA", "IAC", "CONTAINER", "DAST", "SBOM", "PROVENANCE", "VEX"}
    adapters = adapter.get("adapters")
    if not isinstance(adapters, list) or not required.issubset(adapters):
        failures.append("security adapter registry omits a required Batch 40 adapter")
        adapters = []
    if adapter.get("defaultNetwork") != "DENY":
        failures.append("security adapter network must default to DENY")
    if adapter.get("secretValuesInEvidence") is not False:
        failures.append("secret values must be forbidden from evidence")
    if adapter.get("productionMutationAllowed") is not False:
        failures.append("repository security adapters must not authorize production mutation")
    if adapter.get("agentRiskAcceptanceAllowed") is not False:
        failures.append("agents must not accept supply-chain risk")
    if adapter.get("initialStatus") != "NOT_CONFIGURED":
        failures.append("provider adapters must remain NOT_CONFIGURED until a provider is bound")
    active = adapter.get("activeTestAuthorizationRequired")
    if not isinstance(active, list) or "DAST" not in active or "API_SECURITY" not in active:
        failures.append("active DAST and API security tests must require target authorization")
    critical = profile.get("criticalSystem")
    if not isinstance(critical, dict):
        failures.append("critical-system security profile is missing")
        critical = {}
    for flag in ("dualSecurityApproval", "independentAssessment", "killSwitch", "incidentGameDay", "recoveryValidation"):
        if critical.get(flag) is not True:
            failures.append(f"critical-system profile must require {flag}")
    for flag in ("automaticRiskAcceptance", "automaticProductionAuthorization"):
        if critical.get(flag) is not False:
            failures.append(f"critical-system profile must disable {flag}")
    frameworks = profile.get("frameworks", [])
    if "SLSA_1.2" not in frameworks or "NIST_SSDF_1.1" not in frameworks:
        failures.append("security profile must bind SLSA 1.2 and NIST SSDF 1.1")
    return failures, {
        "declaredAdapterCount": len(adapters),
        "requiredAdapters": sorted(required),
        "initialStatus": adapter.get("initialStatus"),
        "defaultNetwork": adapter.get("defaultNetwork"),
        "activeTestAuthorizationRequired": active,
    }


def binding_errors(pack: Path, provenance: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    evidence_id = provenance.get("evidenceId")
    run_report = provenance.get("runReport")
    if not isinstance(evidence_id, str) or not evidence_id:
        return ["provenance evidenceId is required"]
    if not isinstance(run_report, dict):
        return [f"provenance {evidence_id} has no runReport"]
    expected = f"evidence/execution/{evidence_id}.json"
    if run_report.get("path") != expected:
        failures.append(f"provenance {evidence_id} does not bind {expected}")
        return failures
    path = pack / expected
    if not path.is_file():
        failures.append(f"provenance {evidence_id} references missing evidence")
    elif run_report.get("sha256") != sha256_file(path):
        failures.append(f"provenance {evidence_id} digest does not match its evidence")
    return failures


def validate_provenance(pack: Path) -> tuple[list[str], int, bool]:
    directory = pack / "evidence" / "provenance"
    paths = sorted(directory.glob("*.json")) if directory.is_dir() else []
    failures: list[str] = []
    validated = 0
    tamper_rejected = False
    for path in paths:
        record = load_object(path, f"provenance {path.name}")
        errors = binding_errors(pack, record)
        if errors:
            failures.extend(errors)
            continue
        validated += 1
        if not tamper_rejected:
            tampered = copy.deepcopy(record)
            tampered["runReport"]["sha256"] = "sha256:" + "0" * 64
            tamper_rejected = bool(binding_errors(pack, tampered))
    if not paths:
        failures.append("no provenance records are available")
    if not tamper_rejected:
        failures.append("the provenance verifier did not reject a tampered digest")
    return failures, validated, tamper_rejected


def flatten_raw_alerts(value: list[Any]) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, list):
            alerts.extend(entry for entry in item if isinstance(entry, dict))
        elif isinstance(item, dict):
            alerts.append(item)
    return alerts


def build_vex_records(raw_alerts: list[dict[str, Any]]) -> tuple[list[str], list[dict[str, Any]]]:
    failures: list[str] = []
    records: list[dict[str, Any]] = []
    seen: set[int] = set()
    for alert in raw_alerts:
        number = alert.get("number")
        state = alert.get("state")
        dependency = alert.get("dependency") if isinstance(alert.get("dependency"), dict) else {}
        package = dependency.get("package") if isinstance(dependency.get("package"), dict) else {}
        advisory = alert.get("security_advisory") if isinstance(alert.get("security_advisory"), dict) else {}
        if not isinstance(number, int) or number in seen:
            failures.append("Dependabot alert numbers must be present and unique")
            continue
        seen.add(number)
        if state not in {"fixed", "dismissed", "open", "auto_dismissed"}:
            failures.append(f"alert {number} has unsupported state {state}")
            continue
        vex_status = "FIXED" if state == "fixed" else "UNDER_INVESTIGATION"
        records.append({
            "alertNumber": number,
            "vulnerabilityId": advisory.get("ghsa_id") or advisory.get("cve_id") or f"dependabot-alert-{number}",
            "component": package.get("name") or "UNKNOWN",
            "ecosystem": package.get("ecosystem") or "UNKNOWN",
            "manifestPath": dependency.get("manifest_path") or "UNKNOWN",
            "sourceState": state,
            "vexStatus": vex_status,
            "justification": "dependency update recorded by GitHub" if state == "fixed" else None,
            "analysis": (
                "The alert is fixed in the exact GitHub snapshot; deployment applicability remains independently unverified."
                if state == "fixed"
                else "Dismissal or open state is not sufficient evidence for NOT_AFFECTED; applicability review remains open."
            ),
            "evidenceRefs": ["b40-dependabot-alerts"],
        })
    if any(record["vexStatus"] == "NOT_AFFECTED" for record in records):
        failures.append("VEX generation must not infer NOT_AFFECTED from alert state")
    return failures, records


def identities_are_independent(executor: str, verifier: str) -> bool:
    return bool(executor and verifier and executor.strip().casefold() != verifier.strip().casefold())


def analyze(repo: Path, pack: Path, config_path: Path) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    repo = repo.resolve()
    pack = pack.resolve()
    config_path = config_path.resolve()
    if not repo.is_dir() or not pack.is_dir() or not config_path.is_file():
        raise ControlError("repository, pack, and repository-controls config must exist")
    config = load_object(config_path, "repository-controls config")
    controls: list[dict[str, Any]] = []

    def record(control_id: str, capabilities: list[str], statement: str, failures: list[str], details: dict[str, Any] | None = None) -> None:
        controls.append({
            "controlId": control_id,
            "capabilityIds": capabilities,
            "statement": statement,
            "status": "PASS" if not failures else "FAIL",
            "failures": failures,
            "details": details or {},
        })

    config_failures = validate_config(config)
    record("B40-REPOSITORY-CONTROL-SCOPE", list(CAPABILITIES), "The local control scope and external NOT_RUN boundary are exact.", config_failures)

    codeowners = repo / str(config.get("codeownersPath", ""))
    required_patterns = config.get("requiredCodeownerPatterns")
    if not isinstance(required_patterns, list) or not all(isinstance(item, str) and item for item in required_patterns):
        codeowner_failures, owners = ["requiredCodeownerPatterns must be a non-empty string list"], {}
    else:
        codeowner_failures, owners = validate_codeowners(codeowners, required_patterns)
    security_path = repo / str(config.get("securityPolicyPath", ""))
    if not security_path.is_file():
        codeowner_failures.append("SECURITY.md is missing")
    record(
        "B40-SECURE-REVIEW-OWNERSHIP",
        ["b40-secure-code-review-approval"],
        "Every sensitive Batch 40 path has an explicit reviewer owner and a private reporting policy.",
        codeowner_failures,
        {"ownedPatternCount": len(owners), "branchProtection": "NOT_RUN"},
    )

    psirt_path = repo / str(config.get("psirtPolicyPath", ""))
    psirt = load_object(psirt_path, "PSIRT policy")
    psirt_failures = validate_psirt(psirt)
    record(
        "B40-PSIRT-LIFECYCLE",
        ["b40-psirt-security-incident"],
        "The PSIRT lifecycle is owned, bounded, non-automatic, and closure requires verification evidence.",
        psirt_failures,
        {"policyId": psirt.get("policyId"), "externalExerciseStatus": psirt.get("externalExerciseStatus")},
    )

    license_policy_path = repo / str(config.get("licenseReviewPolicyPath", ""))
    license_policy = load_object(license_policy_path, "license review policy")
    dependency_inventory = load_object(
        pack / "evidence/execution/b40-dependency-inventory.json", "dependency inventory"
    )
    license_failures = validate_license_policy(license_policy)
    queue_failures, license_queue = build_license_review_queue(dependency_inventory)
    license_failures.extend(queue_failures)
    record(
        "B40-LICENSE-DECISION-QUEUE",
        [],
        "Every external direct component is retained in a fail-closed legal review queue; no approval is inferred.",
        license_failures,
        {
            "componentCount": len(license_queue),
            "approvedCount": sum(item["decisionStatus"] == "APPROVED" for item in license_queue),
            "policyStatus": license_policy.get("status"),
        },
    )

    adapter = load_object(repo / str(config.get("adapterPolicyPath", "")), "security adapter policy")
    profile = load_object(repo / str(config.get("securityProfilePath", "")), "security profile")
    adapter_failures, adapter_summary = validate_adapter_policies(adapter, profile)
    record(
        "B40-STATIC-AND-IAC-ADAPTER-BOUNDARY",
        ["b40-sast-integration", "b40-container-kubernetes-iac-scanning"],
        "SAST, container, and IaC adapter contracts fail closed until an approved provider is configured.",
        adapter_failures,
        adapter_summary,
    )
    record(
        "B40-ACTIVE-TEST-AUTHORIZATION",
        ["b40-dast-iast-integration"],
        "Active application-security tests require target authorization and remain unconfigured.",
        adapter_failures,
        {"adapterStatus": adapter.get("initialStatus"), "externalExecution": "NOT_RUN"},
    )
    record(
        "B40-ISOLATED-BUILDER-POLICY",
        ["b40-isolated-trusted-builder"],
        "Critical builds require independent assessment and deny automatic production authorization.",
        adapter_failures,
        {"isolatedBuilderExecution": "NOT_RUN", "criticalSystem": profile.get("criticalSystem")},
    )

    provenance_failures, validated_provenance, tamper_rejected = validate_provenance(pack)
    record(
        "B40-CONTENT-ADDRESSED-PROVENANCE",
        ["b40-slsa-provenance", "b40-artifact-container-signing"],
        "Local evidence provenance is content-addressed and the verifier rejects digest tampering.",
        provenance_failures,
        {
            "validatedRecordCount": validated_provenance,
            "tamperNegativeTest": "PASS" if tamper_rejected else "FAIL",
            "slsaBuilderAttestation": "NOT_RUN",
            "productionSignatureVerification": "NOT_RUN",
        },
    )

    certification = load_object(pack / "certification.json", "certification.json")
    identity_failures: list[str] = []
    if certification.get("status") != "NOT_RUN":
        identity_failures.append("repository controls cannot advance certification.status beyond NOT_RUN")
    if identities_are_independent("repository-executor", "repository-executor"):
        identity_failures.append("same-identity independent verification was accepted")
    if not identities_are_independent("repository-executor", "external-verifier-candidate"):
        identity_failures.append("distinct assessment identities were rejected")
    record(
        "B40-INDEPENDENT-ASSESSMENT-BOUNDARY",
        ["b40-independent-security-assessment"],
        "Independent assessment requires a distinct verifier; no repository check can self-promote it.",
        identity_failures,
        {"independentVerification": "NOT_RUN", "certificationStatus": certification.get("status")},
    )

    extensions = config.get("modelArtifactExtensions")
    model_failures: list[str] = []
    if not isinstance(extensions, list) or not extensions or not all(
        isinstance(value, str) and value.startswith(".") for value in extensions
    ):
        extensions = []
        model_failures.append("modelArtifactExtensions must be a non-empty suffix list")
    model_paths = tracked_files(repo, [f"*{suffix}" for suffix in extensions]) if extensions else []
    registry = config.get("modelArtifactRegistry")
    if not isinstance(registry, dict):
        registry = {}
        model_failures.append("modelArtifactRegistry must be an object")
    unregistered = sorted(set(model_paths) - set(registry))
    stale = sorted(set(registry) - set(model_paths))
    if unregistered:
        model_failures.append(f"unregistered model artifacts: {unregistered}")
    if stale:
        model_failures.append(f"model registry entries do not resolve: {stale}")
    for path, entry in registry.items():
        if not isinstance(entry, dict) or not entry.get("digest") or not entry.get("provenanceRef") or not entry.get("owner"):
            model_failures.append(f"model artifact {path} lacks digest, provenanceRef, or owner")
    record(
        "B40-AI-MODEL-ARTIFACT-REGISTRY",
        ["b40-ai-model-supply-chain"],
        "Every tracked deployable model artifact must have an owner, digest, and provenance reference.",
        model_failures,
        {"trackedModelArtifactCount": len(model_paths), "registeredModelArtifactCount": len(registry)},
    )

    raw_path = pack / "evidence/execution/b40-dependabot-alerts.raw.json"
    normalized = load_object(pack / "evidence/execution/b40-dependabot-alerts.json", "Dependabot report")
    raw_alerts = flatten_raw_alerts(load_array(raw_path, "raw Dependabot snapshot"))
    vex_failures, vex_records = build_vex_records(raw_alerts)
    if normalized.get("alertCount") != len(raw_alerts):
        vex_failures.append("raw and normalized Dependabot alert counts differ")
    if normalized.get("openCount") != sum(record["sourceState"] == "open" for record in vex_records):
        vex_failures.append("raw and normalized open-alert counts differ")
    record(
        "B40-VEX-SAFE-MAPPING",
        ["b40-vex-applicability"],
        "Dependabot state is mapped to draft VEX without inferring NOT_AFFECTED from dismissal.",
        vex_failures,
        {
            "recordCount": len(vex_records),
            "fixedCount": sum(record["vexStatus"] == "FIXED" for record in vex_records),
            "underInvestigationCount": sum(record["vexStatus"] == "UNDER_INVESTIGATION" for record in vex_records),
            "notAffectedCount": sum(record["vexStatus"] == "NOT_AFFECTED" for record in vex_records),
        },
    )

    source_targets = tracked_files(repo, [f"*{suffix}" for suffix in SOURCE_SUFFIXES])
    iac_targets = tracked_files(repo, ["Dockerfile", "Dockerfile.*", "*.tf", "*.tfvars", "*/helm/*", "*/k8s/*", "*/kubernetes/*"])
    failed = [control["controlId"] for control in controls if control["status"] != "PASS"]
    capability_results: dict[str, dict[str, Any]] = {}
    for capability in CAPABILITIES:
        related = [control for control in controls if capability in control["capabilityIds"]]
        passed = bool(related) and all(control["status"] == "PASS" for control in related)
        capability_results[capability] = {
            "status": "limited" if passed else "blocked",
            "localControlStatus": "PASS" if passed else "FAIL",
            "controlIds": [control["controlId"] for control in related],
            "boundary": "LOCAL_EXECUTED_SELF_ATTESTED",
            "externalExecution": "NOT_RUN",
            "independentVerification": "NOT_RUN",
            "certificationStatus": "NOT_CERTIFIED",
        }
    return {
        "check": "batch40-repository-controls",
        "batch": 40,
        "status": "PASS" if not failed else "BLOCKED",
        "repositoryRevision": git_revision(repo),
        "startedAt": started_at,
        "finishedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "replayCommand": (
            "uv run --quiet python scripts/batch40_repository_controls.py "
            "--pack mature-product-packs/batch40/elmos-platform-supply-chain"
        ),
        "toolDigest": sha256_file(Path(__file__)),
        "policy": {
            "path": config_path.relative_to(repo).as_posix(),
            "sha256": sha256_file(config_path),
            "policyId": config.get("policyId"),
            "owner": config.get("owner"),
        },
        "scope": {
            "capabilityCount": len(CAPABILITIES),
            "controlCount": len(controls),
            "sourceTargetCount": len(source_targets),
            "containerIacTargetCount": len(iac_targets),
            "modelArtifactCount": len(model_paths),
            "dependabotAlertCount": len(raw_alerts),
        },
        "inputs": {
            "codeownersSha256": sha256_file(codeowners) if codeowners.is_file() else None,
            "securityPolicySha256": sha256_file(security_path) if security_path.is_file() else None,
            "psirtPolicySha256": sha256_file(psirt_path),
            "licenseReviewPolicySha256": sha256_file(license_policy_path),
            "adapterPolicySha256": sha256_file(repo / str(config.get("adapterPolicyPath"))),
            "securityProfileSha256": sha256_file(repo / str(config.get("securityProfilePath"))),
            "dependabotRawSha256": sha256_file(raw_path),
        },
        "controls": controls,
        "failedControls": failed,
        "capabilityResults": capability_results,
        "vexRecords": vex_records,
        "psirtPolicy": psirt,
        "licenseReviewPolicy": license_policy,
        "licenseReviewQueue": license_queue,
        "limitations": [
            "This is bounded repository-owned engineering evidence, not a provider scan, production signature, isolated-builder attestation, independent assessment, approval, or certification.",
            "SAST, DAST/IAST, container, IaC, signing, and isolated-builder adapters remain NOT_CONFIGURED or NOT_RUN; the local result proves their typed fail-closed boundary only.",
            "The model registry covers tracked deployable files with the configured extensions; remote registries, runtime downloads, and embedded model services are not enumerated.",
            "Draft VEX records preserve dismissed and open alerts as UNDER_INVESTIGATION and do not establish deployment reachability or NOT_AFFECTED status.",
            "CODEOWNERS expresses review ownership but branch protection and actual review approvals remain external evidence.",
        ],
        "externalOperationExecuted": False,
        "independentVerification": "NOT_RUN",
        "certificationStatus": "NOT_CERTIFIED",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/batch40-repository-controls.json"),
    )
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    try:
        report = analyze(arguments.repo, arguments.pack, arguments.config)
    except ControlError as exc:
        report = {"check": "batch40-repository-controls", "batch": 40, "status": "INVALID", "error": str(exc)}
        code = 2
    else:
        code = 0 if report["status"] == "PASS" else 3
    payload = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(payload, encoding="utf-8")
        print(f"wrote {arguments.output}")
    else:
        print(payload)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
