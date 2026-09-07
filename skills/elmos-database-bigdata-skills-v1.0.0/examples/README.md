# Runnable decision examples

Each example is a complete, schema-valid input/output set:

- `requirements.json` — workload and governance requirements;
- `database-decision.json` — independently selected roles, alternatives, rejections, evidence and confidence;
- `architecture-decision.json` — primary pattern, secondary patterns, overlays, risks and validation gates;
- `cost-and-eta.json` — autonomous machine wall-clock runtime, human-equivalent effort, HITL delay and token-cost envelope.

Regenerate an example:

```bash
python3 tools/database_selector.py examples/iot-realtime/requirements.json \
  --output examples/iot-realtime/database-decision.json
python3 tools/architecture_selector.py examples/iot-realtime/requirements.json \
  --output examples/iot-realtime/architecture-decision.json
python3 tools/plan_estimator.py examples/iot-realtime/requirements.json \
  --output examples/iot-realtime/cost-and-eta.json
```

These outputs demonstrate deterministic reference behavior. They are not production recommendations until versions, connectors, deployment constraints, representative benchmarks, recovery tests and costs are verified in the target repository.
