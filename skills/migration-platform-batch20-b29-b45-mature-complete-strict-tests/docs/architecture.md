# Architecture decisions in this scaffold

1. **Modular control plane:** the first Java service uses Gradle submodules for contracts, domain, and application code.
2. **Separate execution plane:** the Go runner only receives leased jobs; it does not access the control-plane database.
3. **Separate agent boundary:** the Python service exposes typed planning/execution contracts and can later connect to the model gateway.
4. **Language-engine protocol:** the Maven Java engine produces a PSP-like JSON artifact and never writes platform state.
5. **Transactional metadata:** PostgreSQL owns projects, migrations, tasks, runners, artifacts, inbox/outbox, and audit metadata.
6. **Large artifacts externalized:** the scaffold records artifact paths; production should replace the local path with an object-store adapter.
7. **Long-running work is asynchronous:** the runner claims tasks with a lease and completes with a commit token.
8. **Contract-first:** OpenAPI, AsyncAPI, and JSON Schemas live under `contracts/`.
