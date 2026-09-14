package io.elmos.productionruntime;

import io.elmos.productionruntime.ProductionRuntimeModels.ToolCallReceipt;
import io.elmos.productionruntime.ProductionRuntimeModels.ToolCallRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.ToolCallStatus;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

/** Deployment-specific bridge through the existing durable tool-call authority. */
public final class DeploymentToolExecutor {
    private static final Set<String> ACTIONS = Set.of("policy.evaluate", "target.preflight", "identity.lease_ready",
            "artifact.resolve", "migration.preflight", "migration.apply", "runtime.activate", "health.verify",
            "smoke.verify", "traffic.promote", "rollback.plan", "runtime.restore", "rollback.verify",
            "traffic.apply", "dns.apply", "kubernetes.apply", "tls.rotate", "iac.apply", "iac.destroy",
            "gitops.proposal", "gitops.reconcile", "helm.render");

    public record Request(ToolCallRequest context, String action, byte[] payload) {
        public Request {
            payload = payload.clone();
            if (!ACTIONS.contains(action) || !context.tool().equals("release-deployment:" + action)
                    || payload.length > 262144 || !context.requestHash().equals(hash(payload))) {
                throw new IllegalArgumentException("DEPLOYMENT_TOOL_BINDING_INVALID");
            }
        }
        @Override public byte[] payload() { return payload.clone(); }
    }

    public interface Authorization {
        /** Revalidate current host policy, revocation, workload identity and exact resource lease on every call. */
        void require(Request request);
    }

    public interface Provider {
        /** One bounded send, no retry. Called only after the canonical dispatch claim succeeds. */
        String submit(Request request);
        /** Query the original invocation only; null means still pending. */
        UUID verifiedResponseArtifact(Request request, String providerRequestId);
        /** Independent provider reconciliation; null must preserve UNKNOWN. Must never submit. */
        String reconcile(Request request, UUID toolCallId);
    }

    public interface EvidenceVerifier {
        /** Validate immutable CAS bytes, scope, request hash, invocation and the separate verifier receipt. */
        void require(Request request, String invocation, UUID artifactId);
    }

    public interface ReceiptLookup {
        /** Read the canonical receipt, checking every request context field; null means absent. */
        ToolCallReceipt find(ToolCallRequest request);
    }

    private final ProductionToolCallPort calls;
    private final Authorization authorization;
    private final EvidenceVerifier evidence;
    private final Map<String, Provider> providers;
    private final ReceiptLookup lookup;

    public DeploymentToolExecutor(ProductionToolCallPort calls, Authorization authorization,
                                  EvidenceVerifier evidence, Map<String, Provider> providers, ReceiptLookup lookup) {
        this.calls = java.util.Objects.requireNonNull(calls);
        this.authorization = java.util.Objects.requireNonNull(authorization);
        this.evidence = java.util.Objects.requireNonNull(evidence);
        if (!ACTIONS.containsAll(providers.keySet())) throw new IllegalArgumentException("DEPLOYMENT_PROVIDER_ACTION");
        this.providers = Map.copyOf(providers);
        this.lookup = java.util.Objects.requireNonNull(lookup);
    }

    public ToolCallReceipt tick(Request request) {
        authorization.require(request);
        Provider provider = providers.get(request.action());
        if (provider == null) throw new IllegalStateException("DEPLOYMENT_PROVIDER_NOT_CONFIGURED");
        var context = request.context();
        var receipt = lookup.find(context);
        if (receipt == null) {
            calls.begin(context);
            // Re-read all bindings after a potentially concurrent insert. The generic begin
            // operation checks a hash; this bridge also binds account/project/job/attempt/tool.
            receipt = lookup.find(context);
            if (receipt == null) throw new IllegalStateException("DEPLOYMENT_DURABLE_RECEIPT_MISSING");
        }
        UUID tenant = context.tenantId(), call = receipt.toolCallId();
        if (receipt.status() == ToolCallStatus.COMPLETE) {
            requireInvocation(receipt.providerRequestId());
            if (receipt.responseArtifactId() == null) throw new IllegalStateException("DEPLOYMENT_ARTIFACT_MISSING");
            evidence.require(request,receipt.providerRequestId(),receipt.responseArtifactId());
            return receipt;
        }
        if (receipt.status() == ToolCallStatus.FAILED) return receipt;
        String invocation = receipt.providerRequestId();
        if (receipt.status() == ToolCallStatus.CREATED) {
            // A concurrent claimant or a lost claim response prevents this caller from sending.
            calls.claimProviderDispatch(tenant, call);
            try {
                authorization.require(request);
                invocation = provider.submit(request);
                requireInvocation(invocation);
                calls.markProviderAccepted(tenant, call, invocation);
            } catch (RuntimeException failure) {
                calls.markProviderUnknown(tenant, call, "DEPLOYMENT_SEND_OUTCOME_UNKNOWN");
                return new ToolCallReceipt(call, ToolCallStatus.UNKNOWN, null, null);
            }
        } else if (invocation == null) {
            invocation = provider.reconcile(request, call);
            if (invocation == null) return receipt;
            requireInvocation(invocation);
            calls.markProviderAccepted(tenant, call, invocation);
        }
        authorization.require(request);
        UUID artifact = provider.verifiedResponseArtifact(request, invocation);
        if (artifact == null) return new ToolCallReceipt(call, ToolCallStatus.PROVIDER_ACCEPTED, invocation, null);
        evidence.require(request, invocation, artifact);
        calls.complete(tenant, call, artifact);
        return new ToolCallReceipt(call, ToolCallStatus.COMPLETE, invocation, artifact);
    }

    private static void requireInvocation(String value) {
        if (value == null || !value.matches("[A-Za-z0-9._:-]{1,200}")) {
            throw new IllegalStateException("DEPLOYMENT_INVOCATION_INVALID");
        }
    }

    private static String hash(byte[] value) {
        try { return "sha256:" + HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value)); }
        catch (java.security.NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }
}
