package io.elmos.enterprise;

/**
 * Fail-closed default: no vendor HTTP client exists in this repository for
 * any catalog model yet (see {@code docs/adr/ADR-0059-coding-agent-model-catalog.md}).
 * This probe always reports {@code NOT_IMPLEMENTED} instead of silently
 * returning healthy=false, so the reason a model stayed unprovisioned is
 * distinguishable from "we tried and it was unreachable".
 */
public final class UnimplementedModelHealthProbe implements ModelHealthProbe {
    @Override
    public Result probe(String modelId, String credential) {
        EnterpriseModels.require(modelId, "modelId");
        EnterpriseModels.require(credential, "credential");
        return new Result(false, "HEALTH_PROBE_NOT_IMPLEMENTED", null);
    }
}
