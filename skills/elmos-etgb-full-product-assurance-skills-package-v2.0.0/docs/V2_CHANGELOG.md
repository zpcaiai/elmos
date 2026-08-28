# v2.0.0 Changelog

## Major scope expansion

- Expanded from 4 business lines and 46,664 cases to **30 reported business-line/domain categories and 75,419 cases**.
- Added **23 product domains and 1,452 features** with a machine-readable registry.
- Added **23,232** exact feature cases, **615** cross-domain journey cases and **300** standards-assurance cases.
- Expanded cross-cutting fault injection from 800 to **5,400** cases by applying 100 scenarios at two side-effect positions across 27 domains.
- Added eight product-control smoke cases, bringing offline smoke to 12.
- Expanded Skills from 24 to **50**.
- Added 25 product/journey/standards Adapter contracts.
- Added feature coverage CLI and fail-closed validation.
- Added PostgreSQL feature binding, journey, assurance control, Adapter conformance and gap tables with tenant RLS.
- Added feature, journey, standards and Adapter JSON Schemas.
- Added full-product plans, standards mapping and Adapter implementation status.

## Compatibility

The original four business-line matrices, cases, Skills, CLI and runtime contracts are retained. v2.0 adds governed case files to the suite manifest and broadens the `business_line` schema.

## Honest execution boundary

Local validation executes package tests and 12 offline smoke cases. External cases require real Elmos Adapter implementations and exact environments; they are not reported as executed by this artifact build.
