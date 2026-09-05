# Security Policy

## Supported versions

ELMOS is currently developed from the default branch. Until a separately
published long-term-support policy names a release line, only the latest commit
on the default branch is eligible for security fixes. Tags, forks, historical
commits, generated examples, and experimental packs are not supported release
channels.

| Version | Security fixes |
| --- | --- |
| Default branch HEAD | Supported |
| All other revisions | Not supported unless explicitly named in a security advisory |

## Reporting a vulnerability

Do not open a public issue and do not include credentials, exploit data, or
customer information in a pull request. Report vulnerabilities through a
[private GitHub security advisory](https://github.com/zpcaiai/elmos/security/advisories/new).
Include the affected revision, component, impact, minimal reproduction, and any
known mitigations. If the advisory form is unavailable, contact the repository
owners through an already-established private channel and ask them to open an
advisory; do not send exploit details over a new or unverified channel.

The security maintainers will acknowledge a complete report within 2 business
days, assign an owner and severity within 5 business days, and provide a status
update at least every 7 calendar days while remediation is active. These are
response targets, not a bug-bounty or disclosure-time guarantee.

## Remediation targets

Targets begin when a report is validated and an affected supported revision is
identified. A shorter deadline in a contract or incident policy takes
precedence.

| Severity | Target for a fixed supported revision or documented mitigation |
| --- | --- |
| Critical | 2 calendar days |
| High | 7 calendar days |
| Moderate | 30 calendar days |
| Low | 90 calendar days |

An exception must name the affected component and revision, accountable owner,
expiry, compensating controls, and approval reference. Expired, missing, or
ambiguous exceptions fail closed. Closure requires a fix or mitigation plus
replayable verification; dismissing or suppressing an alert alone is not proof
of remediation.

## Coordinated disclosure

The maintainers and reporter should agree on disclosure timing after a fix is
available to supported users. The repository may publish a GitHub security
advisory with affected versions, severity, remediation, and credit. Never
publish live secrets, customer data, or exploit material that would create
additional risk.

## Evidence boundary

Automated dependency, secret, static, container, or infrastructure scans are
self-attested engineering evidence. A clean scan does not establish that every
vulnerability is absent and does not constitute an independent security
assessment, production approval, or Batch 40 certification.
