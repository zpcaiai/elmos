        # Plan and execute a behavior-preserving refactor

        ## Purpose

        Small reversible changes with linked proof obligations and E3 readiness evidence.

        ## Scope

        invariants → alternatives → DAG → atomic ChangeSets → independent verification

        ## Participating component Skills

        - `business-invariant-recovery`
- `target-architecture-alternatives-and-adr`
- `transformation-dag-estimation`
- `changeset-commit-and-provenance-governance`
- `proof-guided-atomic-refactor-execution`
- `characterization-differential-mutation-verification`
- `e0-e3-readiness-and-evidence-bundle`

        ## Required route contract

        - Bind to one existing canonical route owner.
        - Freeze tenant, engagement, repositories, RevisionSet, environment, data and policy identity.
        - Define acceptance, invariant, evidence, side-effect, rollback and approval obligations before execution.
        - Execute through a durable DAG with atomic ChangeSets and independent verification.
        - Preserve `UNKNOWN`, `UNSUPPORTED`, counterexamples and residual risks.
        - Maximum package-local completion is E3; production execution and E4/E5/P05 are external gates.

        ## Fixture matrix

        Each route requires positive, negative, edge, failure-injection, rollback, stale-evidence, tenant-isolation and unsupported-path fixtures. At least one commercial pilot must exceed 500k LOC; the scale benchmark suite must include a repository over 1M LOC before broad production claims.
