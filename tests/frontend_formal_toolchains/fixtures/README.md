# Frontend formal toolchain fixtures

The focused tests synthesize their exact 9-profile/72-directed-route fixture in
a per-test temporary directory. This avoids checking in generated projects,
dependency locks, or solver output that could become stale while still testing
the full campaign protocol.

The fixture builder is intentionally test-only. Production evidence must come
from `frontend-formal-route-campaign.json` emitted by the frontend engine and
must pass the independent runner without digest rewriting.
