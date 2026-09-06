#!/usr/bin/env python3
"""Record bounded Batch 40 scan results in the pack.

This updates measured engineering evidence only.  It never changes the pack
certification status or manufactures the signed evidence manifest required for
the Batch 40 gate.
"""
import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument(
    'pack', nargs='?', type=Path,
    default=Path('mature-product-packs/batch40/elmos-platform-supply-chain'),
)
parser.add_argument(
    '--skip-context-refresh', action='store_true',
    help='preserve the existing artifact/environment digests when the full repository is not checked out',
)
arguments = parser.parse_args()
P = arguments.pack
inv = json.loads((P / 'evidence/execution/b40-dependency-inventory.json').read_text())
scan = json.loads((P / 'evidence/execution/b40-secret-scan.json').read_text())
dependabot_path = P / 'evidence/execution/b40-dependabot-alerts.json'
dependabot = json.loads(dependabot_path.read_text()) if dependabot_path.is_file() else None
assurance_path = P / 'evidence/execution/b40-local-assurance.json'
assurance = json.loads(assurance_path.read_text()) if assurance_path.is_file() else None
actionable = scan['totals']['actionableFindingCount']
unresolved_license_count = sum(
    1 for component in inv['components']
    if not component.get('internal') and not component.get('licenses')
)


def sha256_file(path: Path) -> str:
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()


def git_revision() -> str | None:
    result = subprocess.run(
        ['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def local_provenance(report: dict, *, evidence_id: str, analyzer: str) -> dict:
    report_path = P / f'evidence/execution/{evidence_id}.json'
    analyzer_path = Path(analyzer)
    return {
        'recordType': 'provenance',
        'schemaVersion': 1,
        'id': f'{evidence_id}-provenance',
        'batch': 40,
        'packKey': 'elmos-platform-supply-chain',
        'evidenceId': evidence_id,
        'status': 'LOCAL_EXECUTED_SELF_ATTESTED',
        'repositoryRevision': report.get('repositoryRevision') or git_revision(),
        'replayCommand': report.get('replayCommand'),
        'runReport': {
            'path': f'evidence/execution/{evidence_id}.json',
            'sha256': sha256_file(report_path),
            'bytes': report_path.stat().st_size,
        },
        'analyzer': {
            'path': analyzer,
            'sha256': sha256_file(analyzer_path),
            'reportedDigest': report.get('toolDigest'),
        },
        'environment': {
            'capturedAt': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'pythonVersion': platform.python_version(),
            'system': platform.system(),
            'machine': platform.machine(),
        },
        'limitations': report.get('limitations', []),
        'externalOperationExecuted': False,
        'independentVerification': 'NOT_RUN',
    }


def preserve_or_create_local_provenance(
    report: dict, *, evidence_id: str, analyzer: str, filename: str,
) -> dict:
    """Do not silently rebind an old report to the current Git revision."""
    path = P / f'evidence/provenance/{filename}'
    report_path = P / f'evidence/execution/{evidence_id}.json'
    current_digest = sha256_file(report_path)
    if path.is_file():
        existing = json.loads(path.read_text())
        if existing.get('runReport', {}).get('sha256') == current_digest:
            return existing
    if not report.get('repositoryRevision'):
        raise SystemExit(
            f'ERROR: changed evidence {evidence_id} has no repositoryRevision; rerun its analyzer'
        )
    return local_provenance(report, evidence_id=evidence_id, analyzer=analyzer)


def dependabot_provenance(report: dict) -> dict:
    raw_path = P / 'evidence/execution/b40-dependabot-alerts.raw.json'
    report_path = P / 'evidence/execution/b40-dependabot-alerts.json'
    return {
        'schemaVersion': 1,
        'id': 'batch40-dependabot-alerts-provenance',
        'batch': 40,
        'packKey': 'elmos-platform-supply-chain',
        'evidenceId': 'b40-dependabot-alerts',
        'status': 'LOCAL_EXECUTED_SELF_ATTESTED',
        'owner': 'elmos-platform-maintainers',
        'source': {
            'repository': report['repository'],
            'commit': report['commit'],
            'endpoint': report['endpoint'],
            'queriedAt': report['queriedAt'],
            'rawSnapshot': {
                'path': 'evidence/execution/b40-dependabot-alerts.raw.json',
                'sha256': sha256_file(raw_path),
                'bytes': raw_path.stat().st_size,
            },
        },
        'runReport': {
            'path': 'evidence/execution/b40-dependabot-alerts.json',
            'sha256': sha256_file(report_path),
            'bytes': report_path.stat().st_size,
        },
        'analyzer': {
            'path': 'scripts/batch40_dependabot_alerts.py',
            'sha256': sha256_file(Path(__file__).with_name('batch40_dependabot_alerts.py')),
        },
        'limitations': report['limitations'],
        'externalOperationExecuted': True,
        'independentVerification': 'NOT_RUN',
    }

evidence = json.loads((P / 'evidence.json').read_text())
evidence['packKey'] = 'elmos-platform-supply-chain'
evidence['claims'] = [
    {"claimId": "b40-declared-dependency-inventory", "status": "PASS",
     "evidenceRefs": ["b40-dependency-inventory"],
     "provenanceRefs": ["batch40-dependency-inventory-provenance"],
     "externalOperationExecuted": False, "authorizationRefs": []},
    {"claimId": "b40-credential-scan-triage",
     # Active findings fail closed. A zero result is still bounded to the exact
     # detector, scope and allowlist recorded by the report.
     "status": "INCONCLUSIVE" if actionable else "PASS",
     "evidenceRefs": ["b40-secret-scan"],
     "provenanceRefs": ["b40-secret-scan-provenance"],
     "externalOperationExecuted": False, "authorizationRefs": []},
]
if dependabot is not None:
    dependabot_status = {
        'PASS': 'PASS',
        'BLOCKED': 'FAIL',
    }.get(dependabot.get('status'), 'INCONCLUSIVE')
    evidence['claims'].append({
        'claimId': 'b40-dependabot-alert-status',
        'status': dependabot_status,
        'evidenceRefs': ['b40-dependabot-alerts'],
        'provenanceRefs': ['batch40-dependabot-alerts-provenance'],
        'externalOperationExecuted': True,
        'authorizationRefs': ['user-request://dependabot-alert-review'],
    })
if assurance is not None:
    evidence['claims'].append({
        'claimId': 'b40-local-assurance-controls',
        'status': 'PASS' if assurance.get('status') == 'PASS' else 'FAIL',
        'evidenceRefs': ['b40-local-assurance'],
        'provenanceRefs': ['b40-local-assurance-provenance'],
        'externalOperationExecuted': False,
        'authorizationRefs': [],
    })
(P / 'evidence.json').write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + '\n')

claims = json.loads((P / 'claims.json').read_text())
claims['status'] = 'PARTIAL'
claims['claims'] = [
    {"claimId": "b40-declared-dependency-inventory",
     "statement": (f"The declared dependency surface is enumerated: {inv['totals']['componentCount']} components "
                   f"from {inv['sources']['mavenPomCount']} Maven POMs and {inv['sources']['npmLockCount']} npm "
                   f"lockfiles; {inv['totals']['versionedExternalCount']} of {inv['totals']['externalComponentCount']} "
                   f"external components have a resolved version."),
     "scope": {"mavenPomCount": inv['sources']['mavenPomCount'],
               "npmLockCount": inv['sources']['npmLockCount'],
               "versionResolution": inv['versionResolution']},
     "limitations": inv['limitations'],
     "evidenceRefs": ["b40-dependency-inventory"]},
    {"claimId": "b40-credential-scan-triage",
     "statement": (f"A credential scan over {scan['coverage']['filesScanned']} files across "
                   f"{len(scan['coverage']['roots'])} declared roots produced {actionable} actionable findings "
                   f"and {scan['totals']['advisoryFindingCount']} advisory high-entropy hits. "
                   f"The scan suppressed {scan['allowlist']['suppressedFindings']} exact fixture matches "
                   f"through {scan['allowlist']['activeEntries']} owned, reasoned, expiring allowlist entries."),
     "scope": {"roots": scan['coverage']['roots'],
               "filesScanned": scan['coverage']['filesScanned'],
               "bySeverity": scan['totals']['bySeverity'],
               "actionablePaths": sorted({f['path'] for f in scan['findings'] if f['severity'] != 'advisory'})},
     "limitations": scan['limitations'] + ([
         "Triage remains outstanding for active findings. Every actionable finding must be fixed or "
         "assigned an exact, owned, reasoned and expiring exception before this claim can pass.",
     ] if actionable else [
         "The zero actionable result is bounded to the declared working-tree scan scope and detector set; "
         "it is not an assertion that no credential exists anywhere or in git history.",
     ]),
     "evidenceRefs": ["b40-secret-scan"]},
]
if dependabot is not None:
    open_count = dependabot['openCount']
    alert_label = 'alert' if open_count == 1 else 'alerts'
    claims['claims'].append({
        'claimId': 'b40-dependabot-alert-status',
        'statement': (
            f"The GitHub Dependabot snapshot for {dependabot['repository']} at commit "
            f"{dependabot['commit']} contains {open_count} open {alert_label} "
            f"out of {dependabot['alertCount']} total alerts; critical open alerts: "
            f"{dependabot['metrics']['criticalVulnerabilityCount']}; high open alerts: "
            f"{dependabot['metrics']['highVulnerabilityCount']}."
        ),
        'scope': {
            'repository': dependabot['repository'],
            'commit': dependabot['commit'],
            'alertCount': dependabot['alertCount'],
            'stateCounts': dependabot['stateCounts'],
            'openBySeverity': dependabot['openBySeverity'],
            'vulnerabilitySla': dependabot.get('vulnerabilitySla'),
        },
        'limitations': dependabot['limitations'],
        'evidenceRefs': ['b40-dependabot-alerts'],
    })
if assurance is not None:
    claims['claims'].append({
        'claimId': 'b40-local-assurance-controls',
        'statement': (
            f"The repository-owned Batch 40 assurance run evaluated "
            f"{assurance['scope']['controlCount']} exact CI and evidence-graph controls; "
            f"{len(assurance.get('failedControls', []))} controls failed."
        ),
        'scope': assurance['scope'],
        'limitations': assurance['limitations'],
        'evidenceRefs': ['b40-local-assurance'],
    })
(P / 'claims.json').write_text(json.dumps(claims, indent=2, ensure_ascii=False) + '\n')

metrics = json.loads((P / 'metrics.json').read_text())
metrics['status'] = 'PARTIAL'
for entry in metrics['metrics']:
    if entry['name'] == 'sbomCoverage':
        entry.update({"measured": True, "value": inv['metrics']['sbomCoverage'],
                      "evidenceRefs": ["b40-dependency-inventory"],
                      "note": "direct declared dependencies only; the transitive Maven graph is not expanded"})
    if dependabot is not None and entry['name'] == 'criticalVulnerabilityCount':
        entry.update({
            'measured': True,
            'value': dependabot['metrics']['criticalVulnerabilityCount'],
            'evidenceRefs': ['b40-dependabot-alerts'],
            'note': 'open critical alerts in the exact GitHub Dependabot snapshot; high and medium counts are recorded separately',
        })
    if (
        dependabot is not None
        and entry['name'] == 'vulnerabilitySlaCompliance'
        and dependabot.get('metrics', {}).get('vulnerabilitySlaCompliance') is not None
    ):
        entry.update({
            'measured': True,
            'value': dependabot['metrics']['vulnerabilitySlaCompliance'],
            'evidenceRefs': ['b40-dependabot-alerts'],
            'note': (
                'fixed Dependabot alerts only; dismissed and auto-dismissed alerts are excluded '
                'pending separate risk-acceptance review'
            ),
        })
    if assurance is not None and entry['name'] in assurance.get('metrics', {}):
        entry.update({
            'measured': True,
            'value': assurance['metrics'][entry['name']],
            'evidenceRefs': ['b40-local-assurance'],
            'note': (
                'bounded to the exact CI workflow and currently declared pack claims; '
                'external and independent assessment remains NOT_RUN'
            ),
        })
(P / 'metrics.json').write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + '\n')

flags = json.loads((P / 'zero-tolerance.json').read_text())
flags['status'] = 'PARTIAL'
for entry in flags['flags']:
    if entry['name'] == 'secretLeaks':
        entry.update({"evaluated": True, "observed": actionable,
                      "evidenceRefs": ["b40-secret-scan"],
                      "note": (f"{actionable} actionable findings await triage across "
                               f"{len(scan['coverage']['roots'])} scanned roots; working tree only, "
                               f"git history not examined")})
    if dependabot is not None and entry['name'] == 'criticalOpenVulnerabilities':
        entry.update({
            'evaluated': True,
            'observed': dependabot['metrics']['criticalVulnerabilityCount'],
            'evidenceRefs': ['b40-dependabot-alerts'],
            'note': 'exact GitHub Dependabot snapshot; independent verification and non-GitHub advisory coverage remain outstanding',
        })
    if assurance is not None and entry['name'] == 'testIntegrityViolations':
        integrity_control = next(
            (
                control for control in assurance.get('controls', [])
                if control.get('controlId') == 'B40-CI-NO-SOFT-FAILURES'
            ),
            None,
        )
        if integrity_control is not None:
            entry.update({
                'evaluated': True,
                'observed': 0 if integrity_control.get('status') == 'PASS' else 1,
                'evidenceRefs': ['b40-local-assurance'],
                'note': (
                    'bounded to continue-on-error enforcement in the exact CI workflow; '
                    'independent corpus and signed evidence integrity remain NOT_RUN'
                ),
            })
    if entry['name'] == 'unresolvedLicenseBlocks':
        entry.update({
            'evaluated': True,
            'observed': unresolved_license_count,
            'evidenceRefs': ['b40-dependency-inventory'],
            'note': (
                f'{unresolved_license_count} external direct components have no resolved license '
                'decision in the bounded inventory; unknown license state fails closed'
            ),
        })
(P / 'zero-tolerance.json').write_text(json.dumps(flags, indent=2, ensure_ascii=False) + '\n')
dependabot_provenance_record = None
if dependabot is not None:
    provenance = P / 'evidence/provenance/batch40-dependabot-alerts-provenance.json'
    dependabot_provenance_record = dependabot_provenance(dependabot)
    provenance.write_text(
        json.dumps(dependabot_provenance_record, indent=2, ensure_ascii=False) + '\n'
    )

provenance_dir = P / 'evidence/provenance'
provenance_dir.mkdir(parents=True, exist_ok=True)
inventory_provenance = preserve_or_create_local_provenance(
    inv,
    evidence_id='b40-dependency-inventory',
    analyzer='scripts/batch40_dependency_inventory.py',
    filename='batch40-dependency-inventory-provenance.json',
)
secret_provenance = preserve_or_create_local_provenance(
    scan,
    evidence_id='b40-secret-scan',
    analyzer='scripts/batch40_secret_scan.py',
    filename='b40-secret-scan-provenance.json',
)
(provenance_dir / 'batch40-dependency-inventory-provenance.json').write_text(
    json.dumps(inventory_provenance, indent=2, ensure_ascii=False) + '\n'
)
(provenance_dir / 'b40-secret-scan-provenance.json').write_text(
    json.dumps(secret_provenance, indent=2, ensure_ascii=False) + '\n'
)
assurance_provenance = None
if assurance is not None:
    assurance_provenance = preserve_or_create_local_provenance(
        assurance,
        evidence_id='b40-local-assurance',
        analyzer='scripts/batch40_local_assurance.py',
        filename='b40-local-assurance-provenance.json',
    )
    (provenance_dir / 'b40-local-assurance-provenance.json').write_text(
        json.dumps(assurance_provenance, indent=2, ensure_ascii=False) + '\n'
    )

artifact_path = P / 'artifact/schema-surface.json'
environment_path = P / 'environment/toolchain.json'
if not arguments.skip_context_refresh:
    declaration_paths = sorted({
        declared
        for component in inv['components']
        for declared in component.get('declaredIn', [])
        if Path(declared).is_file()
    })
    expected_declarations = sorted({
        declared
        for component in inv['components']
        for declared in component.get('declaredIn', [])
    })
    if declaration_paths != expected_declarations:
        missing = sorted(set(expected_declarations) - set(declaration_paths))
        raise SystemExit(
            f'ERROR: {len(missing)} dependency declaration files are unavailable; '
            'use --skip-context-refresh only when preserving an already captured context'
        )
    artifact_members = [
        {
            'path': path,
            'sha256': sha256_file(Path(path)),
            'bytes': Path(path).stat().st_size,
        }
        for path in declaration_paths
    ]
    artifact = {
        'artifactType': 'declared-dependency-surface',
        'memberCount': len(artifact_members),
        'members': artifact_members,
        'mavenBoms': inv['sources'].get('mavenBoms', []),
    }
    artifact['compositeDigest'] = 'sha256:' + hashlib.sha256(
        json.dumps(artifact, sort_keys=True, separators=(',', ':')).encode()
    ).hexdigest()
    artifact_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + '\n')
    environment = {
        'capturedAt': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'os': f'{platform.system()} {platform.release()}',
        'machine': platform.machine(),
        'pythonVersion': platform.python_version(),
        'pythonImplementation': platform.python_implementation(),
        'repositoryRevision': git_revision(),
        'evidenceBoundary': 'LOCAL_EXECUTED_SELF_ATTESTED',
        'independentVerification': 'NOT_RUN',
    }
    environment_path.write_text(json.dumps(environment, indent=2, ensure_ascii=False) + '\n')

pack = json.loads((P / 'pack.json').read_text())
pack['owner'] = 'elmos-platform-maintainers'
pack['status'] = 'experimental'
if not arguments.skip_context_refresh:
    pack['artifactDigest'] = sha256_file(artifact_path)
    pack['environmentDigest'] = sha256_file(environment_path)
pack['evidenceRefs'] = sorted(set(pack.get('evidenceRefs', [])) | {
    'b40-dependency-inventory', 'b40-secret-scan',
    *(['b40-dependabot-alerts'] if dependabot is not None else []),
    *(['b40-local-assurance'] if assurance is not None else []),
})
(P / 'pack.json').write_text(json.dumps(pack, indent=2, ensure_ascii=False) + '\n')

matrix = json.loads((P / 'support-matrix.json').read_text())
limited = {
    'b40-dependency-sca-governance': ['b40-dependabot-alerts'] if dependabot is not None else [],
    'b40-vulnerability-patch-sla': ['b40-dependabot-alerts'] if dependabot is not None else [],
    'b40-sbom-component-identity': ['b40-dependency-inventory'],
    'b40-secret-credential-scanning': ['b40-secret-scan'],
    'b40-secure-sdlc-ssdf': ['b40-local-assurance'] if assurance is not None else [],
    'b40-customer-audit-evidence': ['b40-local-assurance'] if assurance is not None else [],
    'b40-security-supply-chain-gate': ['b40-local-assurance'] if assurance is not None else [],
    'b40-supply-chain-compliance-factory': ['b40-local-assurance'] if assurance is not None else [],
    'b40-threat-modeling': ['b40-local-assurance'] if assurance is not None else [],
    'b40-security-architecture-review': ['b40-local-assurance'] if assurance is not None else [],
    'b40-compliance-control-crosswalk': ['b40-local-assurance'] if assurance is not None else [],
    'b40-runner-update-supply-chain': ['b40-local-assurance'] if assurance is not None else [],
    'b40-license-ip-provenance': ['b40-dependency-inventory'],
}
for capability in matrix['capabilities']:
    capability['owner'] = 'elmos-platform-maintainers'
    refs = limited.get(capability['capabilityId'])
    if refs:
        capability['status'] = 'limited'
        capability['evidenceRefs'] = refs
        capability['notes'] = (
            'Repository-owned bounded engineering evidence only; external and independent evidence is NOT_RUN.'
        )
(P / 'support-matrix.json').write_text(json.dumps(matrix, indent=2, ensure_ascii=False) + '\n')

sbom_record = json.loads((P / 'sbom-record.json').read_text())
sbom_record.update({
    'status': 'draft',
    'evidenceRefs': ['b40-dependency-inventory'],
    'records': [{
        'scope': 'direct Maven and npm declarations',
        'componentCount': inv['totals']['componentCount'],
        'externalComponentCount': inv['totals']['externalComponentCount'],
        'versionedExternalCount': inv['totals']['versionedExternalCount'],
        'coverage': inv['metrics']['sbomCoverage'],
        'transitiveGraph': 'NOT_RUN',
        'independentVerification': 'NOT_RUN',
    }],
})
(P / 'sbom-record.json').write_text(json.dumps(sbom_record, indent=2, ensure_ascii=False) + '\n')

provenance_record = json.loads((P / 'provenance-record.json').read_text())
all_provenance = [inventory_provenance, secret_provenance]
all_provenance_refs = ['b40-dependency-inventory', 'b40-secret-scan']
if dependabot_provenance_record is not None:
    all_provenance.append(dependabot_provenance_record)
    all_provenance_refs.append('b40-dependabot-alerts')
if assurance_provenance is not None:
    all_provenance.append(assurance_provenance)
    all_provenance_refs.append('b40-local-assurance')
provenance_record.update({
    'status': 'draft',
    'evidenceRefs': all_provenance_refs,
    'records': all_provenance,
})
(P / 'provenance-record.json').write_text(
    json.dumps(provenance_record, indent=2, ensure_ascii=False) + '\n'
)

if assurance is not None:
    crosswalk = json.loads((P / 'control-crosswalk.json').read_text())
    crosswalk.update({
        'status': 'draft',
        'evidenceRefs': ['b40-local-assurance'],
        'records': [
            {
                'controlId': control['controlId'],
                'statement': control['statement'],
                'status': control['status'],
                'evidenceRefs': ['b40-local-assurance'],
                'boundary': 'LOCAL_EXECUTED_SELF_ATTESTED',
            }
            for control in assurance['controls']
        ],
    })
    (P / 'control-crosswalk.json').write_text(
        json.dumps(crosswalk, indent=2, ensure_ascii=False) + '\n'
    )
    if assurance.get('threatModel'):
        threat_model = json.loads((P / 'threat-model.json').read_text())
        threat_model.update({
            'status': 'draft',
            'evidenceRefs': ['b40-local-assurance'],
            'records': assurance['threatModel']['threats'],
            'metadata': {
                'modelId': assurance['threatModel']['id'],
                'scope': assurance['threatModel']['scope'],
                'expectedThreatCount': assurance['threatModel']['expectedThreatCount'],
                'completeThreatCount': assurance['threatModel']['completeThreatCount'],
                'independentVerification': 'NOT_RUN',
            },
        })
        (P / 'threat-model.json').write_text(
            json.dumps(threat_model, indent=2, ensure_ascii=False) + '\n'
        )
if dependabot is not None:
    assurance_label = assurance.get('status') if assurance is not None else 'NOT_RUN'
    print(f"batch40 已记录: sbomCoverage={inv['metrics']['sbomCoverage']} "
          f"secretLeaks={actionable} dependabotOpen={dependabot['openCount']} "
          f"localAssurance={assurance_label} "
          f"(advisory {scan['totals']['advisoryFindingCount']} 不计入)")
else:
    print(f"batch40 已记录: sbomCoverage={inv['metrics']['sbomCoverage']} secretLeaks={actionable} "
          f"(advisory {scan['totals']['advisoryFindingCount']} 不计入)")
