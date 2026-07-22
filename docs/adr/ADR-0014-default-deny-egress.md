# ADR-0014: Default-deny sandbox egress

Status: Accepted

## Decision

Workspaces start on internal networks with no external route. A versioned, time-bounded policy may permit exact HTTPS dependency hosts through an enforcing proxy. DNS answers are checked against forbidden address classes and direct IP/bypass traffic is denied.

## Consequences

Docker internal networking supplies the default deny layer but not domain enforcement. Approved egress is unavailable until proxy integration proves allowed-host success and direct bypass failure.
