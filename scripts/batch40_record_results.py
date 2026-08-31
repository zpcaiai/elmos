#!/usr/bin/env python3
"""Record bounded Batch 40 scan results in the pack.

This updates measured engineering evidence only.  It never changes the pack
certification status or manufactures the signed evidence manifest required for
the Batch 40 gate.
"""
import hashlib
import json
import sys
from pathlib import Path

P = Path(sys.argv[1] if len(sys.argv) > 1 else 'mature-product-packs/batch40/elmos-platform-supply-chain')
inv = json.loads((P / 'evidence/execution/b40-dependency-inventory.json').read_text())
scan = json.loads((P / 'evidence/execution/b40-secret-scan.json').read_text())
dependabot_path = P / 'evidence/execution/b40-dependabot-alerts.json'
dependabot = json.loads(dependabot_path.read_text()) if dependabot_path.is_file() else None
actionable = scan['totals']['actionableFindingCount']


def sha256_file(path: Path) -> str:
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()


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
     # Findings exist and nobody has triaged them, so the claim is INCONCLUSIVE.
     # Calling it PASS would require deciding on the owner's behalf that every
     # hit is a test fixture; calling it FAIL would assert leaks that may not exist.
     "status": "INCONCLUSIVE" if actionable else "PASS",
     "evidenceRefs": ["b40-secret-scan"],
     "provenanceRefs": ["batch40-dependency-inventory-provenance"],
     "externalOperationExecuted": False, "authorizationRefs": []},
]
if dependabot is not None:
    evidence['claims'].append({
        'claimId': 'b40-dependabot-alert-status',
        'status': 'PASS' if dependabot.get('status') == 'PASS' else 'INCONCLUSIVE',
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
                   f"The actionable findings are untriaged: none has been confirmed as a live credential "
                   f"or dismissed as a fixture."),
     "scope": {"roots": scan['coverage']['roots'],
               "filesScanned": scan['coverage']['filesScanned'],
               "bySeverity": scan['totals']['bySeverity'],
               "actionablePaths": sorted({f['path'] for f in scan['findings'] if f['severity'] != 'advisory'})},
     "limitations": scan['limitations'] + [
         "Triage is outstanding. Every actionable finding must be either fixed or added to "
         "config/secret-scan-allowlist.json with a reason, an owner and an expiry before this claim can pass.",
     ],
     "evidenceRefs": ["b40-secret-scan"]},
]
if dependabot is not None:
    claims['claims'].append({
        'claimId': 'b40-dependabot-alert-status',
        'statement': (
            f"The GitHub Dependabot snapshot for {dependabot['repository']} at commit "
            f"{dependabot['commit']} contains {dependabot['openCount']} open alerts "
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
            'note': 'open critical alerts in the exact GitHub Dependabot snapshot; high and moderate counts are recorded separately',
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
    print(f"batch40 已记录: sbomCoverage={inv['metrics']['sbomCoverage']} "
          f"secretLeaks={actionable} dependabotOpen={dependabot['openCount']} "
          f"(advisory {scan['totals']['advisoryFindingCount']} 不计入)")
else:
    print(f"batch40 已记录: sbomCoverage={inv['metrics']['sbomCoverage']} secretLeaks={actionable} "
          f"(advisory {scan['totals']['advisoryFindingCount']} 不计入)")
