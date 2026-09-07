# Metrics Catalog

Recommended metric names:

```text
elmos_formal_proof_runs_total{engine,property_kind,status,criticality}
elmos_formal_proof_wall_clock_seconds{engine,property_kind,mode}
elmos_formal_queue_delay_seconds{criticality}
elmos_formal_unknown_ratio{engine,property_kind}
elmos_formal_counterexamples_total{business_line,property_kind}
elmos_formal_cache_hits_total{business_line}
elmos_formal_cache_invalidations_total{dependency_kind}
elmos_formal_evidence_age_seconds{assurance_level}
elmos_formal_gate_decisions_total{gate,decision,reason_class}
elmos_formal_waivers_active{risk}
elmos_formal_fencing_rejections_total{operation}
elmos_formal_credit_micros{phase}
elmos_formal_eta_absolute_error_seconds{engine,property_kind}
```

Do not label by tenant, source path, formula, SQL text, counterexample or artifact URI. Tenant-specific views are produced from authorized database queries, not global metric cardinality.
