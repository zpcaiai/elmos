# Batch 32 version and lifecycle policy

- Source and target versions must be exact. `latest`, `*`, broad major ranges, and unbounded provider versions are prohibited in certified packs.
- Framework, language, runtime, build, package manager, router, renderer, state, forms, styling, design system, API client, identity, i18n, tests, browser, OS, and device versions are independently recorded.
- Changes to source or target versions, providers, browsers, devices, rendering, security, design system, accessibility, acceptance profile, or visual baseline policy trigger recertification.
- Target profiles require a maintenance owner, security-update policy, supported-browser policy, dependency-lock policy, and deprecation path.
- Multiple exact tuples may be certified only when each has evidence. One passing tuple does not certify a family.
- Reverse routes and alternate target profiles are separate packs.
- Legacy bridges, native sidecars, coexistence layers, and compatibility components require owners and exit criteria.
