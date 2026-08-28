# Elmos Continuous Agent Certification

**Status:** not-certified  
**Owner:** `domain-pack.project-generation`  

## Commercial objective

Production agent, RAG or multi-agent system with changing models, prompts, datasets, tools or providers is transformed into the declared targets without transferring semantic, execution or completion authority to a provider.

## Mandatory execution

1. curate-eval-dataset
1. calibrate-judges
1. capture-provider-fingerprint
1. run-shadow-eval
1. detect-drift
1. recertify-or-rollback
1. seal-certificate

## Native evidence

- dataset lineage and holdout isolation
- judge calibration
- provider fingerprint
- side-effect-free shadow comparison
- drift decision
- re-certification or rollback proof

## Holdout and negative cases

- silent model drift
- judge self-preference
- quality gain with cost/SLO regression
- production-data consent failure

## Completion boundary

The route may be reported as structurally available after package validation, but only an independent K8 certificate bound to current native evidence may report E5/P05 completion.
