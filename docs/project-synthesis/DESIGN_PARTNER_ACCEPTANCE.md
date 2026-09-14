# Design-partner acceptance for multilingual project generation

This is the intake a design partner signs. It is not certification. An Agent
cannot complete the signature block.

## Required partners

At least two independent organizations. The same consultancy, the same parent
company, or the repository maintainers do not count as two.

## Each partner records

| Field | Partner A | Partner B |
| --- | --- | --- |
| Legal name | | |
| Independent organization identifier | | |
| Business scenario and acceptance criteria | | |
| Private infrastructure / region | | |
| Generated language, framework, auth and database tuple | | |
| Exact ELMOS commit and engine-source SHA-256 | | |
| Evidence-bundle SHA-256 | | |
| Date of exercise | | |
| Actor (not the ELMOS executor) | | |
| Functional result | | |
| Security / tenant-isolation result | | |
| Build, startup and operational result | | |
| Expected versus actual run cost | | |
| Support effort and elapsed delivery time | | |
| Accepted? (`YES` / `NO`) | | |
| Blocking defects | | |
| Signer name, role and external signature | | |

## Fail-closed rules

- Empty signature blocks keep `independent_verification_status=NOT_RUN`.
- A maintainer cannot sign as both producer and partner.
- Passing the local 16-case matrix does not fill this form.
- Synthetic companies, repository fixtures and Agent-authored signatures are invalid.
- Both partners must accept the exact release subject; mixed commits do not close the gate.
- Unit economics must include Runner, model, storage, egress, human review and support costs.
