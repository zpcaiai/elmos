# Semantic Preservation Contract

ELMOS defines conversion correctness as a scoped semantic relation, not text similarity. For each route, enumerate the input domain, source-defined/undefined/implementation-defined behavior, externally observable effects, permitted target refinements, and proof/test obligations. A target can pass only inside the characterized source domain.

A CompCert-style preservation principle is used as the high-assurance reference: if conversion succeeds on an in-scope source program, target observable behavior must refine an allowed source behavior under declared assumptions. This package does not claim a machine-checked proof for all ELMOS routes.
