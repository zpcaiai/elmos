# Vue 3 fixture to WeChat native candidate

This Batch 32 client pack is intentionally limited to the versioned
`vue3-todo-source-snapshot-1.0.1` source snapshot (derived from the
`elmos-frontend-to-miniapp-skills-v1.0.0` fixture) and one target profile: a
WeChat native MiniApp candidate.

The pack records local static inventory, typed UI Interaction IR evidence, and
a replayable local conversion that generated an 11-file WeChat candidate with
deterministic static validation. The runtime IR and the 20-node Batch 32 review
model are deliberately recorded as separate models.

The source snapshot has exact dependency locks and a locally replayed
typecheck/build. It does not claim that the source application was launched,
that an official WeChat build succeeded, or that emulator, physical-device,
accessibility, visual, performance, holdout, upload, review, or release checks
ran. Those target and external states remain `NOT_RUN`; readiness is
`NOT_READY`, and the pack remains `experimental` and `NOT_CERTIFIED`.

This directional pack does not cover reverse conversion, other frontend
fixtures, other source framework versions, Alipay, Douyin, Xiaohongshu, WebView,
full-page Canvas, payment, upload, review, or release authorization.
