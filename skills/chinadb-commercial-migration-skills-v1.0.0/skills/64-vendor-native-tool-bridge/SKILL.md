# Vendor-Native Migration Tool Bridge

- **Skill ID:** `64-vendor-native-tool-bridge`
- **Version:** `1.0.0`
- **Category:** integration
- **Implementation status:** specification only until repository evidence proves otherwise

## Objective

Wrap vendor-native migration/assessment tools as optional providers while normalizing their outputs into the platform evidence model and avoiding vendor lock-in in the core architecture.

## Inputs

- Tool availability/license/API/CLI
- Route manifest
- Vendor tool config

## Required outputs

- Provider capabilities
- Normalized progress/events
- Imported assessment/conversion findings
- Evidence links
- Fallback path

## Implementation modules / repository contract

- vendor_tools/base.py
- vendor_tools/dm.py
- vendor_tools/kingbase.py
- vendor_tools/opengauss.py
- vendor_tools/gbase.py
- vendor_tools/highgo.py
- vendor_tools/oceanbase.py
- vendor_tools/gaussdb.py
- vendor_tools/goldendb.py

## Workflow

1. Discover tool version/capability safely.
2. Generate config without embedded secrets.
3. Run/import status through adapter-specific provider.
4. Normalize findings without treating vendor success as E3/E4/E5 proof.
5. Fall back to generic engine where supported.

## Mandatory tests

- Tool missing
- License unavailable
- Partial failure
- Resume/retry
- Vendor output schema change

## Required evidence

- Vendor tool version
- Normalized evidence
- Raw-log reference/redacted hash

## Definition of Done

- Actual implementation exists in the product repository; no stub-only completion.
- Required unit/integration fixtures execute in CI and include negative cases.
- Evidence artifacts conform to schemas/evidence.schema.json and reference real logs/results.
- No silent semantic fallback: unsupported or ambiguous cases are explicit.
- Documentation, config schema and route/version compatibility declarations are updated.
- The skill's release gate is reproducible from a clean checkout.
