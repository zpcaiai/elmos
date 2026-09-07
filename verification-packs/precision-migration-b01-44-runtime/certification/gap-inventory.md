# Gap inventory

- Execute domain-native operations for non-B16 Skills; their exact allowlisted handler contracts pass, but contract execution is not domain execution.
- Extend real native source/target builds beyond the 30 bounded B16 routes and their exact version tuples.
- Have an independent verifier rerun the frozen holdout corpus; local B16 holdout passes, independent status is `NOT_RUN`.
- Run real customer language, framework, client, database, and production-scale workloads; bounded representative B16 fixtures pass, customer status is `NOT_RUN`.
- Integrate and execute production HSM/key custody, identity, revocation, retention, and operational monitoring; local OpenSSL Ed25519 signing passes, HSM status is `NOT_RUN`.
- Execute authorized Canary and rollback against a real deployment; current status is `NOT_RUN`.
- Resolve all P0 residual risks before requesting certification.
