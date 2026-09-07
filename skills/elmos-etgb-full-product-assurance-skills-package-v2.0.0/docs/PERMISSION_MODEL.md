# Permission and authority model

ETGB uses Environment-owned or Attachment-owned authority. An authority snapshot is immutable for its owner and includes tenant, role, capabilities, filesystem roots, network policy, secret references, hidden-test rights, fencing token and expiry.

## Fail-closed decision

A tool request is authorized only when all identity bindings match and the requested capability/resource is granted. There is no fallback to Thread-wide permission. Redirects, subprocesses, MCP/tool calls and resumed sessions must remain under the same owning authority.

## Hidden-test boundary

Transformation and generation workers cannot read, write or execute hidden tests. Validation workers can execute hidden tests but cannot mutate target/source or reveal hidden content to the model. Release workers consume digested results and disclosure-safe evidence.

## Secret handling

Tools request named secret references. The policy service resolves only allowed references into the owning Environment. Secret values are not placed in Prompts, traces, metrics, checkpoints or evidence reports.

## Reference assets

- schema: `schemas/environment-authority.schema.json`;
- evaluator: `etgb/policy.py`;
- examples: `integrations/policy/`;
- negative tests: cross-cutting authority, hidden-test, tenant and secret scenarios.
