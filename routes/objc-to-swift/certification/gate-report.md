# objc-to-swift route gate

- Local bounded profile: `PASSED`
- Route status: `limited`
- Native source analyzer: `PASSED`
- Native target compiler/runtime: `PASSED`
- Development, holdout, and representative behavior: `PASSED`
- Five-function typed-pure module composition (integer/finite-number/boolean): `PASSED`
- Input domain: `canonical-finite-no-error-input-domain`
- String semantics and number arithmetic: `BLOCKED`
- Independent verifier: `NOT_RUN`
- External/customer certification: `NOT_RUN`

The route is supported only for `typed-pure-function-v1` plus `typed-pure-module-v1`. Local zero-unknown claims apply only to integer, finite-number transport/comparison, and boolean semantics inside the canonical finite no-error input domain. Repository orchestration may process many eligible work units, but unsupported units keep the repository result `PARTIAL`; unsupported semantics and undeclared directed routes fail closed.
