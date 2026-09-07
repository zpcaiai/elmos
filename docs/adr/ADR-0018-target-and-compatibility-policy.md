# ADR-0018: Target and compatibility policy

Status: Accepted

## Decision

Java 21 remains the default ELMOS modernization target. Java 17 and Java 25 are selectable only through an organization policy. Exact Spring Boot, Spring Cloud, build plugin and database targets must come from an approved, versioned compatibility matrix; a scanner recommendation cannot silently select the newest available release.

Compatibility decisions retain source version, target version, matrix version, rationale and evidence status. Missing source fingerprints or matrix entries create blocking evidence gates.

