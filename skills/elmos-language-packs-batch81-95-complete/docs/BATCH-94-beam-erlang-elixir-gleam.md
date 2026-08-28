# Batch 94: Erlang / Elixir / Gleam BEAM Pack

Generates and modernizes OTP applications, supervision trees, distributed clusters, Phoenix systems, and fault-injection tests.

## Skills

- PG379 `beam-project-discovery-and-inventory`
- PG380 `erlang-parser-and-otp-model`
- PG381 `elixir-mix-project-profile`
- PG382 `gleam-project-profile`
- PG383 `otp-supervision-tree-generator`
- PG384 `genserver-state-machine-generator`
- PG385 `distributed-node-cluster-topology-planner`
- PG386 `beam-messaging-backpressure-generator`
- PG387 `ets-mnesia-data-modeler`
- PG388 `phoenix-liveview-api-generator`
- PG389 `beam-property-concurrency-fault-test-generator`
- PG390 `beam-release-upgrade-certifier`

## Safety boundary

Fault tolerance must be demonstrated under process crashes, node partitions, overload, and rolling release upgrades—not inferred from using OTP.

## Principal risks

- mailbox overload
- supervision restart storm
- distributed partition
- state upgrade incompatibility
- process leak
- message ordering assumption
