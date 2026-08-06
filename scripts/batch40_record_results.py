#!/usr/bin/env python3
"""Record the Batch 40 scan results in the pack. Planning-neutral: no status granted."""
import json, sys
from pathlib import Path

P = Path(sys.argv[1] if len(sys.argv) > 1 else 'mature-product-packs/batch40/elmos-platform-supply-chain')
inv = json.loads((P / 'evidence/execution/b40-dependency-inventory.json').read_text())
scan = json.loads((P / 'evidence/execution/b40-secret-scan.json').read_text())
actionable = scan['totals']['actionableFindingCount']

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
(P / 'claims.json').write_text(json.dumps(claims, indent=2, ensure_ascii=False) + '\n')

metrics = json.loads((P / 'metrics.json').read_text())
metrics['status'] = 'PARTIAL'
for entry in metrics['metrics']:
    if entry['name'] == 'sbomCoverage':
        entry.update({"measured": True, "value": inv['metrics']['sbomCoverage'],
                      "evidenceRefs": ["b40-dependency-inventory"],
                      "note": "direct declared dependencies only; the transitive Maven graph is not expanded"})
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
(P / 'zero-tolerance.json').write_text(json.dumps(flags, indent=2, ensure_ascii=False) + '\n')
print(f"batch40 已记录: sbomCoverage={inv['metrics']['sbomCoverage']} secretLeaks={actionable} "
      f"(advisory {scan['totals']['advisoryFindingCount']} 不计入)")
