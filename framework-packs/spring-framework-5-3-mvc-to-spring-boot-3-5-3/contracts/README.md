# Contract layout

`framework-contract-model.json` is the authoritative static FCM. Each domain
subdirectory records the same fail-closed execution boundary. Static modeling is
not behavior evidence; every domain remains `NOT_RUN` until source and target
contract replay succeeds.
