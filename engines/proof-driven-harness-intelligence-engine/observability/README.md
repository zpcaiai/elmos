# Observability contract

The process-local service exposes only low-cardinality HTTP counters and never
uses tenant, project, actor, path, prompt, token, or source content as metric
labels. `/metrics` requires `pdhi.control.observe`; scrapers must use the same
trusted identity boundary as other protected APIs.

The remaining metrics in `metric-contract.yaml` are required production-host
adapter outputs. Their presence in this directory is not execution evidence.
Collector export, alert delivery, paging, retention, dashboards, and telemetry
backend verification remain `NOT_RUN`.
