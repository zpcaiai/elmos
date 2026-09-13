import copy
from dataclasses import replace
import pytest
from elmos_assurance.core import evaluate, digest, canonical, strict_loads
from tests.support import valid_fixture, modify_report, modify_payload, sign, NOW


def run(f): return evaluate(f.request,f.envelopes,f.blobs,f.context,NOW)
def blocked(f):
    r=run(f)
    assert r['verdict']!='PASS',r
    assert r['production_signing_allowed'] is False
    return '\n'.join(r['reasons'])


def test_valid_synthetic_case_is_only_a_demo():
    r=run(valid_fixture())
    assert r['verdict']=='PASS'
    assert r['kind']=='DEMO_ONLY_NOT_A_CERTIFICATE'
    assert r['production_signing_allowed'] is False

@pytest.mark.parametrize('field', ['source','target','artifact','scope','contract','policy','environment','toolchain','suite','data','comparator','rules'])
def test_any_revision_mutation_invalidates_approval(field):
    f=valid_fixture();f.request['revision_set'][field]=digest('changed')
    assert 'REQUEST_NOT_APPROVED' in blocked(f)

@pytest.mark.parametrize('field,value',[('tenant_id','other'),('project_id','other'),('run_id','other'),('builder_control_domain','other')])
def test_unapproved_request_identity_changes(field,value):
    f=valid_fixture();f.request[field]=value
    assert 'REQUEST_NOT_APPROVED' in blocked(f)

@pytest.mark.parametrize('field', ['tenant_id','project_id','run_id'])
def test_cross_subject_even_validly_signed_evidence_is_rejected(field):
    f=valid_fixture();modify_payload(f,'build',lambda p:p.update({field:'other'}))
    assert 'SUBJECT_IDENTITY_MISMATCH' in blocked(f)

@pytest.mark.parametrize('kind', ['build','contract','smoke','regression','differential','mutation','proof','audit'])
def test_missing_required_evidence_is_not_pass(kind):
    f=valid_fixture();f.envelopes=[e for e in f.envelopes if e['payload']['kind']!=kind]
    assert 'SEALED_EVIDENCE_INVENTORY_MISMATCH' in blocked(f)

@pytest.mark.parametrize('kind', ['build','regression','proof','audit'])
def test_tampered_signature_payload_rejected(kind):
    f=valid_fixture();modify_payload(f,kind,lambda p:p.update(expires_at=NOW+200),resign=False)
    assert 'EVIDENCE_REJECTED' in blocked(f)

@pytest.mark.parametrize('stamp_field,value',[('expires_at',NOW),('issued_at',NOW+1)])
def test_expired_or_future_evidence_rejected(stamp_field,value):
    f=valid_fixture();modify_payload(f,'regression',lambda p:p.update({stamp_field:value}))
    assert 'EVIDENCE_STALE_OR_FUTURE' in blocked(f)


def test_raw_blob_corruption_rejected():
    f=valid_fixture();h=f.envelopes[0]['payload']['report_digest'];f.blobs[h]=b'{}'
    assert 'REPORT_DIGEST_MISMATCH' in blocked(f)


def test_raw_blob_missing_rejected():
    f=valid_fixture();f.blobs.pop(f.envelopes[0]['payload']['report_digest'])
    assert 'REPORT_MISSING' in blocked(f)


def test_empty_obligations_rejected():
    f=valid_fixture();f.request['obligations']=[]
    assert 'SCHEMA_INVALID' in blocked(f)


def test_duplicate_obligation_rejected_even_if_approved():
    f=valid_fixture();f.request['obligations'].append(copy.deepcopy(f.request['obligations'][0]))
    f.context=replace(f.context,approved_request_digest=digest(f.request))
    assert 'DUPLICATE_OBLIGATION' in blocked(f)


def test_empty_trusted_inventory_rejected():
    f=valid_fixture();f.context=replace(f.context,expected_evidence_ids=frozenset())
    assert 'EMPTY_OR_INVALID_EVIDENCE_INVENTORY' in blocked(f)


def test_duplicate_evidence_rejected():
    f=valid_fixture();f.envelopes.append(copy.deepcopy(f.envelopes[0]))
    assert 'DUPLICATE_EVIDENCE_ID' in blocked(f)


def test_revoked_request_rejected():
    f=valid_fixture();f.context=replace(f.context,revoked_request_digests=frozenset({digest(f.request)}))
    assert 'REQUEST_REVOKED' in blocked(f)


def test_revoked_signer_rejected():
    f=valid_fixture();keys=dict(f.context.keys);keys['demo-ethen']=replace(keys['demo-ethen'],revoked=True)
    f.context=replace(f.context,keys=keys)
    assert 'SIGNER_REVOKED_OR_EXPIRED' in blocked(f)


def test_unknown_signer_cannot_self_register():
    f=valid_fixture();f.envelopes[-1]['key_id']='repo-provided-root'
    assert 'UNTRUSTED_SIGNER' in blocked(f)


def test_runner_signing_audit_is_not_authorized():
    f=valid_fixture();f.envelopes[-1]=sign('demo-runner',f.envelopes[-1]['payload'],f.private_keys)
    assert 'SIGNER_KIND_NOT_AUTHORIZED' in blocked(f)


def test_separate_key_same_control_domain_is_not_external_audit():
    f=valid_fixture();keys=dict(f.context.keys);keys['demo-ethen']=replace(keys['demo-ethen'],control_domain='demo-builder')
    f.context=replace(f.context,keys=keys)
    assert 'AUDITOR_NOT_INDEPENDENT_CONTROL_DOMAIN' in blocked(f)


def test_auditor_control_domain_requires_operator_approval():
    f=valid_fixture();f.context=replace(f.context,approved_auditor_domains=frozenset())
    assert 'AUDITOR_DOMAIN_NOT_APPROVED' in blocked(f)


def test_hidden_failure_cannot_be_omitted_from_sealed_inventory():
    f=valid_fixture();modify_report(f,'regression',lambda r:r['results'][0].update(status='FAIL'))
    assert run(f)['verdict']=='FAIL'
    f.envelopes=[e for e in f.envelopes if e['payload']['kind']!='regression']
    assert 'SEALED_EVIDENCE_INVENTORY_MISMATCH' in blocked(f)


def test_zero_assertions_do_not_count_as_pass():
    f=valid_fixture();modify_report(f,'regression',lambda r:r['results'][0].update(assertions=0))
    assert 'CASE_NOT_VERIFIED' in blocked(f)


def test_unknown_case_does_not_count_as_pass():
    f=valid_fixture();modify_report(f,'regression',lambda r:r['results'][0].update(status='INCONCLUSIVE'))
    assert 'CASE_NOT_VERIFIED' in blocked(f)


def test_test_manifest_substitution_rejected():
    f=valid_fixture();modify_report(f,'regression',lambda r:r['results'][0].update(case_id='different-case'))
    assert 'EXECUTED_CASE_MANIFEST_MISMATCH' in blocked(f)


def test_duplicate_case_cannot_inflate_execution():
    f=valid_fixture();modify_report(f,'regression',lambda r:r['results'].append(dict(r['results'][0])))
    assert 'EXECUTED_CASE_MANIFEST_MISMATCH' in blocked(f)


def test_open_critical_finding_wins_over_all_green_flags():
    f=valid_fixture();modify_report(f,'regression',lambda r:r['findings'].append({'id':'auth-bypass','severity':'critical','state':'OPEN','message':'Synthetic counterexample'}))
    assert run(f)['verdict']=='FAIL'

@pytest.mark.parametrize('check',['statement_matches','axioms_approved','artifact_binding_verified','preconditions_verified','independent_checker_verified'])
def test_formal_unverified_property_blocks(check):
    f=valid_fixture();modify_report(f,'proof',lambda r:r['proof_checks'].update({check:False}))
    assert 'FORMAL_STATEMENT_AXIOM_BINDING_OR_CHECKER_UNVERIFIED' in blocked(f)


def test_mutation_unknown_not_killed():
    f=valid_fixture();modify_report(f,'mutation',lambda r:r['mutation_checks'].update(unknown=1))
    assert 'MUTATION_UNKNOWN' in blocked(f)


def test_empty_mutation_is_not_100_percent():
    f=valid_fixture();modify_report(f,'mutation',lambda r:r['mutation_checks'].update(killed=0))
    assert 'MUTATION_EMPTY_DENOMINATOR' in blocked(f)


def test_critical_mutant_survivor_fails():
    f=valid_fixture();modify_report(f,'mutation',lambda r:r['mutation_checks'].update(must_kill_survived=1))
    assert run(f)['verdict']=='FAIL'


def test_unreviewed_equivalent_exclusion_blocks():
    f=valid_fixture();modify_report(f,'mutation',lambda r:r['mutation_checks'].update(equivalent=3,exclusions_reviewed=False))
    assert 'MUTATION_EXCLUSIONS_UNREVIEWED' in blocked(f)


def test_stale_audit_cannot_cover_new_evidence():
    f=valid_fixture();modify_report(f,'smoke',lambda r:r['results'][0].update(assertions=2),refresh_audit=False)
    assert 'AUDIT_BASIS_MISMATCH' in blocked(f)


def test_same_count_different_discovered_interface_blocks():
    f=valid_fixture();modify_report(f,'audit',lambda r:r['audit_checks'].update(discovery_diff_count=2))
    assert 'INDEPENDENT_DISCOVERY_MISMATCH' in blocked(f)


def test_no_audit_challenge_blocks():
    f=valid_fixture();modify_report(f,'audit',lambda r:r['audit_checks'].update(challenge_count=0,challenge_passed=0))
    assert 'AUDIT_CHALLENGE_INSUFFICIENT' in blocked(f)


def test_failed_audit_challenge_fails():
    f=valid_fixture();modify_report(f,'audit',lambda r:r['audit_checks'].update(challenge_passed=2))
    assert run(f)['verdict']=='FAIL'

@pytest.mark.parametrize('raw',[b'{"x":1,"x":2}', b'{"x":NaN}',b'{"x":1.1}',b'{"x":Infinity}'])
def test_ambiguous_json_rejected(raw):
    with pytest.raises(ValueError): strict_loads(raw)

@pytest.mark.parametrize('value',[float('nan'),0.1,{1:'key'},2**60])
def test_unsupported_canonical_values_rejected(value):
    with pytest.raises(ValueError):canonical(value)


def test_unknown_schema_field_cannot_set_force_pass():
    f=valid_fixture();f.request['force_pass']=True
    assert 'SCHEMA_INVALID' in blocked(f)


def test_same_key_cannot_impersonate_two_independent_domains():
    f=valid_fixture();keys=dict(f.context.keys)
    keys['demo-ethen']=replace(keys['demo-ethen'],public_key=keys['demo-runner'].public_key)
    f.context=replace(f.context,keys=keys)
    assert 'CRYPTO_KEY_SHARED_ACROSS_CONTROL_DOMAINS' in blocked(f)
