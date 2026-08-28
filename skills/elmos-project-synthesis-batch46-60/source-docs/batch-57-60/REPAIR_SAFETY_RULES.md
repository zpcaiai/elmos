# Repair Safety Rules

Automated repair is allowed only when all of the following hold:

- The likely root cause has concrete compiler, test, trace, contract, or policy evidence.
- The change is limited to managed or merge-approved protected artifacts.
- Acceptance criteria, public contracts, business rules, security policy, and architecture remain unchanged.
- File-count, change-ratio, attempts, duration, and cost stay under configured limits.
- The repair does not delete, disable, skip, quarantine, or weaken required tests.
- The repair does not introduce unapproved dependencies, repositories, permissions, or network access.
- Impacted and required regression checks run after the change.

Mandatory stop conditions:

- Repeated root cause with no progress.
- Need to modify user-owned code.
- Need to change an approved contract or data migration semantics.
- Security or tenant-isolation uncertainty.
- Repair limit exhaustion.
- Conflicting evidence about the root cause.
