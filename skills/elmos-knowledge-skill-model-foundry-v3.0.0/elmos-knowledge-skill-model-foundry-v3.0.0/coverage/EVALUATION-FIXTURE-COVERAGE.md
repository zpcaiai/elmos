# Evaluation Fixture Coverage

- Atomic Skills: **1310**
- Positive activation cases: **10480**
- Negative activation cases: **10480**
- Ambiguous routing cases: **5240**
- Adversarial cases: **5240**
- Total activation/routing/security cases: **31440**

Every Skill has a versioned `evals/contract.yaml`, `evals/cases.yaml`, execution policy and conformance manifest. Cases establish a minimum fixture floor only; production certification still requires domain-specific repository, database, runtime, device, workload and customer acceptance suites.

Evaluation splits must be disjoint by repository, organization and time. Model judgment may supplement but never override deterministic hard failures.
