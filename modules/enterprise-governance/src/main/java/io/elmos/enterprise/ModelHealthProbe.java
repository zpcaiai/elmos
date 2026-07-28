package io.elmos.enterprise;

/**
 * Verifies that a credential actually works against the vendor before an
 * endpoint may be marked {@code approved=true, healthy=true}. A real
 * implementation would make one bounded, side-effect-free call to the
 * vendor's API (e.g. a models/list or lightweight completion call) and
 * translate the result into a {@link Result}; it must never guess "healthy"
 * from the mere presence of a credential.
 */
public interface ModelHealthProbe {
    record Result(boolean healthy, String reasonCode, String evidenceRef) {
        public Result {
            EnterpriseModels.require(reasonCode, "reasonCode");
        }
    }

    /**
     * @throws RuntimeException implementations may throw on transport
     * failure; callers must treat that identically to
     * {@code healthy=false} rather than letting an exception escape as a
     * false "configured" state.
     */
    Result probe(String modelId, String credential);
}
