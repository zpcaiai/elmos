# Worker Runtime

Worker processes are disposable.

Required durable state:
- immutable input snapshot
- dispatch intent
- attempt
- lease/fence
- checkpoint
- artifacts
- model/tool calls

## Addressability

If scheduler dispatches to a named worker:
- register worker endpoint + instance id;
- use headless service / StatefulSet identity or equivalent;
- never rely on random service load balancing.

## Safe points

Checkpoint:
- after repository discovery
- after module/batch boundaries
- before and after build/test
- after repair cycles
- before cooperative pause/cancel acknowledgement
