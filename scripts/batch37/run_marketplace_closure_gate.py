#!/usr/bin/env python3
from __future__ import annotations
import subprocess
import sys
import json
from pathlib import Path
from _common import load, resolve_ref, validate_attested_corpus


def main() -> int:
    pack = Path(sys.argv[1])
    failures: list[str] = []
    here = Path(__file__)
    checks = [
        ('validate_marketplace_closure.py', [str(pack)]),
    ]
    certification_checks = [
        ('validate_dependency_lock.py', [str(pack / 'dependencies/lock.json')]),
        ('validate_runtime_health.py', [str(pack / 'runtime/health.json')]),
        ('validate_catalog_governance.py', [str(pack / 'catalog')]),
        ('validate_publisher_lifecycle.py', [str(pack / 'publishers/lifecycle.json')]),
        ('validate_continuous_certification.py', [str(pack / 'certification/recertification-policy.json')]),
        ('validate_extension_migration.py', [str(pack / 'migrations/extension-migration.json')]),
        ('validate_continuity_plan.py', [str(pack / 'continuity/revocation-plan.json')]),
        ('validate_legal_support.py', [str(pack / 'legal-support/policy.json')]),
        ('validate_private_marketplace.py', [str(pack / 'private-marketplace/policy.json')]),
        ('validate_offline_mirror.py', [str(pack / 'offline-mirror/policy.json')]),
        ('validate_marketplace_operations.py', [str(pack / 'operations/operations-policy.json')]),
        ('validate_commercial_settlement.py', [str(pack / 'commercial/settlement.json')]),
        ('validate_eol_policy.py', [str(pack / 'lifecycle/eol-policy.json')]),
    ]
    for script, args in checks:
        proc = subprocess.run(
            [sys.executable, str(here.with_name(script)), *args],
            stdout=subprocess.DEVNULL,
            check=False,
        )
        if proc.returncode:
            failures.append(f'{script} failed')

    try:
        manifest = load(pack / 'pack.json')
        evidence = load(pack / 'certification/evidence.json')
        core_cert = load(pack / 'certification/certification.json')
        closure_cert = load(pack / 'certification/closure-certification.json')
        extension = load(pack / 'extensions/sample/manifest.json')
        sandbox = load(pack / 'sandbox/policy.json')
        publisher = load(pack / manifest['contracts']['publisher_profile'])
        release = load(pack / 'releases/sample/release.json')
        commercial = load(pack / 'commercial/policy.json')
    except Exception as exc:
        print(f'CLOSURE GATE FAIL: {exc}', file=sys.stderr)
        return 2

    requested = (
        manifest.get('status') == 'certified'
        or core_cert.get('status') == 'certified'
        or closure_cert.get('status') == 'certified'
        or release.get('status') in {'certified', 'published'}
    )
    if requested:
        for script, args in certification_checks:
            proc = subprocess.run(
                [sys.executable, str(here.with_name(script)), *args],
                stdout=subprocess.DEVNULL,
                check=False,
            )
            if proc.returncode:
                failures.append(f'{script} failed')
    if manifest.get('status') != core_cert.get('status'):
        failures.append('pack and core certification status mismatch')
    if manifest.get('status') != closure_cert.get('status'):
        failures.append('pack and closure certification status mismatch')

    if requested:
        if evidence.get('external_evidence_status') != 'PASSED':
            failures.append('core external_evidence_status must be PASSED for certification')
        closure_contracts = [
            'dependencies/lock.json', 'runtime/health.json', 'catalog/catalog-entry.json',
            'catalog/ranking-policy.json', 'publishers/lifecycle.json',
            'certification/recertification-policy.json', 'migrations/extension-migration.json',
            'continuity/revocation-plan.json', 'legal-support/policy.json',
            'private-marketplace/policy.json', 'offline-mirror/policy.json',
            'operations/operations-policy.json', 'commercial/settlement.json',
            'lifecycle/eol-policy.json',
        ]
        for relative in closure_contracts:
            if load(pack / relative).get('evidence_status') != 'PASSED':
                failures.append(f'{relative} evidence_status must be PASSED for certification')
        core_metrics: dict[str, object] = {}
        core_metrics.update(evidence.get('metrics', {}))
        core_metrics.update(core_cert.get('metrics', {}))
        core_thresholds = {
            'abi_conformance_rate': 1.0,
            'sdk_conformance_rate': 1.0,
            'sandbox_conformance_rate': 1.0,
            'extension_build_pass_rate': 1.0,
            'negative_security_pass_rate': 1.0,
            'signature_verification_rate': 1.0,
            'sbom_provenance_coverage': 1.0,
            'publisher_verification_rate': 1.0,
            'compatibility_matrix_pass_rate': 1.0,
            'install_upgrade_rollback_pass_rate': 1.0,
            'revocation_enforcement_rate': 1.0,
            'entitlement_metering_reconciliation_rate': 1.0,
            'holdout_pass_rate': 1.0,
            'representative_extension_pass_rate': 1.0,
            'evidence_trace_coverage': 0.95,
        }
        for key, threshold in core_thresholds.items():
            if float(core_metrics.get(key, 0)) < threshold:
                failures.append(f'core {key} below {threshold}')
        core_zero: dict[str, object] = {}
        core_zero.update(evidence.get('zero_tolerance', {}))
        core_zero.update(core_cert.get('zero_tolerance', {}))
        for key in [
            'critical_unknowns', 'sandbox_escapes', 'cross_tenant_access',
            'undeclared_permission_grants', 'unsigned_published_releases',
            'tampered_artifacts_accepted', 'critical_vulnerabilities',
            'prohibited_license_findings', 'unverified_active_publishers',
            'revoked_release_executions', 'orphaned_credentials',
            'billing_reconciliation_breaks', 'self_approved_critical_waivers',
            'test_integrity_violations', 'missing_p0_evidence',
        ]:
            if core_zero.get(key, 1) != 0:
                failures.append(f'core {key} must be zero')
        for rel in ['corpus/negative', 'corpus/holdout', 'corpus/representative-extensions']:
            validate_attested_corpus(pack, rel, failures)
        if publisher.get('verified') is not True or publisher.get('status') != 'active':
            failures.append('publisher must be verified and active')
        if not publisher.get('signing_identities') or not any(
            item.get('status') == 'active' for item in publisher.get('signing_identities', [])
        ):
            failures.append('active publisher signing identity required')
        if release.get('status') not in {'certified', 'published'}:
            failures.append('release must be certified or published')
        if release.get('immutable') is not True:
            failures.append('release must be immutable')
        if sandbox.get('default_action') != 'deny':
            failures.append('sandbox must deny by default')
        if commercial.get('metering_authority') != 'platform' or commercial.get('security_gate_independent') is not True:
            failures.append('commercial policy cannot control security gate')
        core_refs = evidence.get('evidence_refs', []) + core_cert.get('evidence_refs', [])
        if not core_refs:
            failures.append('core certification evidence refs empty')
        for ref in core_refs:
            if not resolve_ref(pack, ref):
                failures.append(f'missing core evidence ref: {ref}')

        closure_thresholds = {
            'dependency_resolution_pass_rate': 1.0,
            'runtime_reconciliation_pass_rate': 1.0,
            'catalog_governance_pass_rate': 1.0,
            'publisher_lifecycle_pass_rate': 1.0,
            'continuous_certification_pass_rate': 1.0,
            'migration_rollback_pass_rate': 1.0,
            'continuity_pass_rate': 1.0,
            'legal_support_pass_rate': 1.0,
            'private_marketplace_pass_rate': 1.0,
            'offline_mirror_pass_rate': 1.0,
            'operations_dr_pass_rate': 1.0,
            'settlement_reconciliation_pass_rate': 1.0,
            'eol_portability_pass_rate': 1.0,
            'closure_holdout_pass_rate': 1.0,
            'representative_lifecycle_pass_rate': 1.0,
            'evidence_trace_coverage': 0.95,
        }
        for key, threshold in closure_thresholds.items():
            if float(closure_cert.get('metrics', {}).get(key, 0)) < threshold:
                failures.append(f'{key} below {threshold}')
        for key in [
            'dependency_cycles', 'revoked_dependency_activations', 'runtime_drift',
            'open_critical_incidents', 'overdue_p0_certifications',
            'failed_state_migrations', 'continuity_gaps',
            'open_blocking_legal_cases', 'open_p0_sla_breaches',
            'cross_tenant_private_marketplace_access', 'stale_revocation_mirrors',
            'dr_reconciliation_breaks', 'settlement_differences',
            'fraud_findings_open', 'residual_eol_dependencies',
            'customers_stranded_at_eol', 'missing_closure_evidence',
        ]:
            if closure_cert.get('zero_tolerance', {}).get(key, 1) != 0:
                failures.append(f'{key} must be zero')
        for rel in ['corpus/closure-holdout', 'corpus/representative-lifecycle']:
            validate_attested_corpus(pack, rel, failures)
        if not closure_cert.get('evidence_refs'):
            failures.append('closure evidence refs empty')
        for ref in closure_cert.get('evidence_refs', []):
            if not resolve_ref(pack, ref):
                failures.append(f'missing closure evidence ref: {ref}')

    status = 'failed' if failures else 'passed'
    decision = 'BLOCKED' if failures else ('CERTIFIED' if requested else 'NOT_CERTIFIED')
    result = {
        'schema_version': 1,
        'pack_key': manifest.get('pack_key'),
        'status': status,
        'pack_status': manifest.get('status'),
        'structural_gate_status': status,
        'certification_requested': requested,
        'closure_decision': decision,
        'closure_complete': requested and not failures,
        'failures': failures,
    }
    (pack / 'certification/closure-gate-result.json').write_text(json.dumps(result, indent=2) + '\n')
    lines = [
        f'# Batch 37 closure gate: {manifest.get("pack_key")}', '',
        f'- Pack status: `{manifest.get("status")}`',
        f'- Closure structural gate status: `{status}`',
        f'- Certification requested: `{str(requested).lower()}`',
        f'- Closure decision: `{decision}`', '',
    ]
    lines += (
        ['## Failures'] + [f'- {item}' for item in failures]
        if failures else (
            ['Core and closure lifecycle certification checks passed.']
            if requested else
            ['Structural checks passed; closure certification was not requested and remains `NOT_CERTIFIED`.']
        )
    )
    (pack / 'certification/closure-gate-report.md').write_text('\n'.join(lines) + '\n')
    if failures:
        print('\n'.join('CLOSURE GATE FAIL: ' + item for item in failures), file=sys.stderr)
        return 2
    print(f'CLOSURE GATE PASS: {manifest.get("pack_key")} status={manifest.get("status")} decision={decision}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
