# Business Line 4 / Batch 32 closure matrix

This matrix separates repository implementation from platform, device, release,
independent-verification, and production-certification evidence. Local code and
tests cannot promote any external state.

| Area | Repository implementation | Local state | External state |
|---|---|---|---|
| Official toolchains | Exact, permit-bound plans for WeChat `miniprogram-ci` compile-result/preview/upload and Alipay `minidev` build/preview/upload; broker receipts are tuple-, tenant-, artifact-, and idempotency-bound | Implemented and tested | `NOT_RUN` |
| Douyin/Xiaohongshu toolchains | Explicit blocked plans; no command is invented without an exact account-tested tuple | Fail-closed | `NOT_RUN` |
| Source semantics | Main MiniApp semantic IR handles `computed`, `watch`, `watchEffect`, `useReducer`, lifecycle effects, deep state paths, and platform APIs; unsupported semantics remain typed findings | Implemented bounded slices | Representative framework builds/devices `NOT_RUN` |
| Target platform generation | Four distinct native project structures; unsupported Douyin/Xiaohongshu tuples remain blockers | Static generation tested | Official build/device `NOT_RUN` |
| Business/native APIs | Fail-closed ports for identity/privacy, payment, share/subscription, LBS/map, media/RTC managers, filesystem, camera, BLE, and Canvas | Generated adapter tests passed | Real accounts/hardware `NOT_RUN` |
| Hardware runtime | BLE, camera, canvas, and payment may simulate only when mock mode is explicitly requested; normal mode throws `NATIVE_CAPABILITY_UNAVAILABLE` when the native SDK is absent | Negative and mock tests passed | Android/iOS matrix `NOT_RUN` |
| Compliance | Secret, dynamic code, remote script, sensitive logging, permission disclosure, and platform privacy authorization-aspect scans | Static audit tested | Platform review `NOT_RUN` |
| Headless safety | Project-root realpath containment, allowlisted module loading, VM timeouts, and string/Wasm code generation disabled | Escape tests passed | Independent penetration test `NOT_RUN` |
| Client Packs | WeChat reference Pack retained as experimental; Alipay directional Pack scaffolded with exact tuple and named owners; claimed web-console certification downgraded to truthful experimental state | Schema validation passed | Full Alipay evidence closure `NOT_RUN` |
| 72 frontend routes | Existing typed IR, generated profiles, bounded formal campaign, and channel declarations retained | Local campaign covered by engine tests | Browser/Android/iOS/Harmony runtime matrix `NOT_RUN` |
| Certification | Business-line runner is read-only local qualification; conservative gate requires an operator trust root outside the repository for a certified request | Self-certification path removed | Independent certification `NOT_CERTIFIED` |

## External closure inputs

The remaining work cannot be generated inside the repository. It requires
authorized platform accounts and credentials, installed exact official tools,
real browser/device runners, independent holdout/representative corpora,
penetration/chaos/production/customer evidence, and an independent certification
authority. Until those inputs are supplied, all corresponding fields must remain
`NOT_RUN` and production status must remain `NOT_CERTIFIED`.
