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
| Workspace / generated target | | |
| Date of exercise | | |
| Actor (not the ELMOS executor) | | |
| Accepted? (`YES` / `NO`) | | |
| Blocking defects | | |
| Signature | | |

## Fail-closed rules

- Empty signature blocks keep `independent_verification_status=NOT_RUN`.
- A maintainer cannot sign as both producer and partner.
- Passing the local 16-case matrix does not fill this form.
