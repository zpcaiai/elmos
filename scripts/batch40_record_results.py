#!/usr/bin/env python3
"""Record bounded Batch 40 scan results in the pack.

This updates measured engineering evidence only.  It never changes the pack
certification status or manufactures the signed evidence manifest required for
the Batch 40 gate.
"""
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

P = Path(sys.argv[1] if len(sys.argv) > 1 else 'mature-product-packs/batch40/elmos-platform-supply-chain')
inv = json.loads((P / 'evidence/execution/b40-dependency-inventory.json').read_text())
scan = json.loads((P / 'evidence/execution/b40-secret-scan.json').read_text())
dependabot_path = P / 'evidence/execution/b40-dependabot-alerts.json'
dependabot = json.loads(dependabot_path.read_text()) if dependabot_path.is_file() else None
actionable = scan['totals']['actionableFindingCount']


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
        'repositoryRevision': git_revision(),
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


def dependabot_provenance(report: dict) -> dict:
    raw_path = P / 'evidence/execution/b40-dependabot-alerts.raw.json'
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
        },
        'limitations': dependabot['limitations'],
        'evidenceRefs': ['b40-dependabot-alerts'],
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
(P / 'zero-tolerance.json').write_text(json.dumps(flags, indent=2, ensure_ascii=False) + '\n')
if dependabot is not None:
    provenance = P / 'evidence/provenance/b40-dependabot-alerts-provenance.json'
    provenance.write_text(json.dumps(dependabot_provenance(dependabot), indent=2, ensure_ascii=False) + '\n')

provenance_dir = P / 'evidence/provenance'
provenance_dir.mkdir(parents=True, exist_ok=True)
inventory_provenance = local_provenance(
    inv,
    evidence_id='b40-dependency-inventory',
    analyzer='scripts/batch40_dependency_inventory.py',
)
secret_provenance = local_provenance(
    scan,
    evidence_id='b40-secret-scan',
    analyzer='scripts/batch40_secret_scan.py',
)
(provenance_dir / 'batch40-dependency-inventory-provenance.json').write_text(
    json.dumps(inventory_provenance, indent=2, ensure_ascii=False) + '\n'
)
(provenance_dir / 'b40-secret-scan-provenance.json').write_text(
    json.dumps(secret_provenance, indent=2, ensure_ascii=False) + '\n'
)

declaration_paths = sorted({
    declared
    for component in inv['components']
    for declared in component.get('declaredIn', [])
    if Path(declared).is_file()
})
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
artifact_path = P / 'artifact/schema-surface.json'
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
environment_path = P / 'environment/toolchain.json'
environment_path.write_text(json.dumps(environment, indent=2, ensure_ascii=False) + '\n')

pack = json.loads((P / 'pack.json').read_text())
pack['owner'] = 'elmos-platform-maintainers'
pack['status'] = 'experimental'
pack['artifactDigest'] = sha256_file(artifact_path)
pack['environmentDigest'] = sha256_file(environment_path)
pack['evidenceRefs'] = sorted(set(pack.get('evidenceRefs', [])) | {
    'b40-dependency-inventory', 'b40-secret-scan',
    *(['b40-dependabot-alerts'] if dependabot is not None else []),
})
(P / 'pack.json').write_text(json.dumps(pack, indent=2, ensure_ascii=False) + '\n')

matrix = json.loads((P / 'support-matrix.json').read_text())
limited = {
    'b40-dependency-sca-governance': ['b40-dependabot-alerts'] if dependabot is not None else [],
    'b40-sbom-component-identity': ['b40-dependency-inventory'],
    'b40-secret-credential-scanning': ['b40-secret-scan'],
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
provenance_record.update({
    'status': 'draft',
    'evidenceRefs': ['b40-dependency-inventory', 'b40-secret-scan'],
    'records': [inventory_provenance, secret_provenance],
})
(P / 'provenance-record.json').write_text(
    json.dumps(provenance_record, indent=2, ensure_ascii=False) + '\n'
)
if dependabot is not None:
    print(f"batch40 已记录: sbomCoverage={inv['metrics']['sbomCoverage']} "
          f"secretLeaks={actionable} dependabotOpen={dependabot['openCount']} "
          f"(advisory {scan['totals']['advisoryFindingCount']} 不计入)")
else:
    print(f"batch40 已记录: sbomCoverage={inv['metrics']['sbomCoverage']} secretLeaks={actionable} "
          f"(advisory {scan['totals']['advisoryFindingCount']} 不计入)")
