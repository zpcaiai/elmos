# Batch 91: Salesforce Apex / SOQL / LWC Pack

Generates and modernizes Salesforce metadata, Apex logic, queries, automation, UI, packages, and release pipelines.

## Skills

- PG343 `salesforce-org-metadata-discovery`
- PG344 `apex-parser-and-semantic-model`
- PG345 `soql-sosl-query-analyzer`
- PG346 `trigger-bulkification-governor-limit-analyzer`
- PG347 `lwc-application-generator`
- PG348 `visualforce-to-lwc-modernizer`
- PG349 `flow-apex-orchestration-generator`
- PG350 `platform-event-integration-generator`
- PG351 `salesforce-security-sharing-fsl-crud-generator`
- PG352 `sfdx-package-ci-generator`
- PG353 `apex-test-mutation-generator`
- PG354 `salesforce-release-certifier`

## Safety boundary

CRUD, field-level security, sharing, tenant boundaries, and governor limits are mandatory correctness properties rather than optional optimizations.

## Principal risks

- governor-limit breach
- sharing/FLS bypass
- trigger recursion
- bulkification failure
- metadata dependency gap
- org-specific assumption
