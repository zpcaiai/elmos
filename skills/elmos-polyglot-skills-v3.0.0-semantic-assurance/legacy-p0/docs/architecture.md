# Legacy P0 architecture

The extension adds semantic domains missing from a modern-language-only compiler: record/byte layout, transaction monitor behavior, batch/job semantics, terminal/desktop UI state, 4GL database abstractions, numerical kernels, safety contracts and native ABI. Every conversion route must select the minimum IR set needed to preserve observable behavior.

## Route principle

A matrix cell means **a planned semantic path can be constructed**, not that a direct emitter exists. Low-fitness destinations can be rejected by policy. Commercial certification is route+profile+repository+runtime specific.
