# Validation Report

Package: `elmos-formal-assurance-kernel-v1.0.0`  
Generated: `2026-08-27`  
Status: **PASS**

## Executed checks

| Check | Result | Detail |
|---|---|---|
| required-root-files | PASS |  |
| yaml-parse | PASS | 238 plain YAML files;  |
| helm-template-contracts | PASS | 6 templates;  |
| json-parse | PASS | 37 files;  |
| skill-contracts | PASS | 60 skills, 300 files;  |
| skill-dependency-dag | PASS | 60 nodes |
| skill-priority-domain | PASS | priority={'P0': 48, 'P1': 10, 'P2': 2}, domain={'project-generation': 9, 'core': 10, 'platform': 11, 'cross-language': 10, 'sql-conversion': 10, 'spring-modernization': 10} |
| json-schema-meta-validation | PASS | 17 schemas;  |
| contract-examples | PASS | 16 examples;  |
| verifier-adapters | PASS | 17 adapters;  |
| workflows | PASS | 10 workflows;  |
| install-profiles | PASS | 7 profiles;  |
| golden-routes | PASS | 5 routes;  |
| postgres-migrations | PASS | 4 ordered migrations |
| rego-policy-contracts | PASS | 6 modules, 6 tests (OPA execution is external) |
| package-manifest-counts | PASS | {'skills': 60, 'perSkillFiles': 300, 'jsonSchemas': 17, 'schemaExamples': 16, 'postgresMigrations': 4, 'openApiContracts': 4, 'asyncApiContracts': 1, 'regoModules': 6, 'regoTests': 6, 'verifierAdapters': 17, 'workflows': 10, 'goldenRoutes': 5, 'installProfiles': 7} |
| generated-catalog | PASS | registry=60, index=60, skills=60 |
| local-markdown-links | PASS | 0 broken;  |
| python-compile | PASS | reference kernel and scripts |
| reference-kernel-tests | PASS | 40 tests;  |
| reference-kernel-demo | PASS | {   "proved": "ALLOW",   "boundedForA2": "DENY",   "honesty": "bounded result remains bounded and is denied for an A2 obligation" } |
| installer-roundtrip | PASS | installed 212 files; manifest: /tmp/tmps94tt66j/elmos/.elmos/formal-assurance-install-manifest.json
 removed 212, restored 0, preserved modified 0 |

## Warnings

- 18 release-time digest placeholders remain by design

## Interpretation

The validation confirms package structure, dependency DAGs, contract/schema examples, reference-kernel behavior, installer safety and static policy content. It does not execute external proof engines, OPA, PostgreSQL, container, Helm/Kubernetes or customer Golden Routes.
