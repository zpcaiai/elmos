package io.elmos.controlplane;

import com.fasterxml.jackson.core.StreamReadFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import io.elmos.cas.CasDigest;
import io.elmos.cas.TenantCasStore;
import io.elmos.productionruntime.DeploymentToolExecutor;
import java.nio.charset.StandardCharsets;
import java.security.PublicKey;
import java.security.Signature;
import java.time.Clock;
import java.util.Base64;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

/** Verifies real CAS bytes and an externally signed, exact-scope decision. Never signs. */
public final class DeploymentCasEvidenceVerifier implements DeploymentToolExecutor.EvidenceVerifier {
    public record Binding(CasDigest artifact, CasDigest statement, String producer,
                          String producerKeyDigest, String verifierKeyId, String signature) {}
    /** Resolve only through authenticated artifact ownership and immutable evidence indexes. */
    public interface Bindings { Binding resolve(DeploymentToolExecutor.Request request, String invocation, UUID artifact); }
    public record Verifier(String principal, PublicKey key) {}
    /** Must consult current revocation, not a cached status from publication time. */
    public interface Trust { Verifier requireCurrent(String keyId); }
    private final TenantCasStore cas;
    private final Bindings bindings;
    private final Trust trust;
    private final Clock clock;

    public DeploymentCasEvidenceVerifier(TenantCasStore cas, Bindings bindings, Trust trust, Clock clock) {
        this.cas=Objects.requireNonNull(cas); this.bindings=Objects.requireNonNull(bindings);
        this.trust=Objects.requireNonNull(trust); this.clock=Objects.requireNonNull(clock);
    }

    @Override public void require(DeploymentToolExecutor.Request request, String invocation, UUID artifactId) {
        try {
            Binding binding=Objects.requireNonNull(bindings.resolve(request,invocation,artifactId));
            check(binding.artifact().sizeBytes() > 0 && binding.artifact().sizeBytes() <= 4_194_304
                    && binding.statement().sizeBytes() > 0 && binding.statement().sizeBytes() <= 65_536);
            var store=cas.forTenant(request.context().tenantId().toString());
            byte[] artifact=store.get(binding.artifact()), statement=store.get(binding.statement());
            check(binding.artifact().matches(artifact) && binding.statement().matches(statement));
            Verifier verifier=trust.requireCurrent(binding.verifierKeyId());
            check(verifier != null && verifier.principal() != null && !verifier.principal().isBlank()
                    && binding.producer() != null && !binding.producer().isBlank()
                    && !verifier.principal().equals(binding.producer())
                    && binding.producerKeyDigest() != null && binding.producerKeyDigest().matches("sha256:[0-9a-f]{64}")
                    && !binding.producerKeyDigest().equals("sha256:"+CasDigest.of(verifier.key().getEncoded()).hex()));
            Signature signature=Signature.getInstance("Ed25519");
            check(binding.signature() != null && binding.signature().length() <= 128);
            signature.initVerify(verifier.key());
            signature.update("elmos.deployment.independent-evidence.v1\n".getBytes(StandardCharsets.UTF_8));
            signature.update(statement);
            check(signature.verify(Base64.getDecoder().decode(binding.signature())));
            JsonNode body=JsonMapper.builder().enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
                    .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS).build().readTree(statement);
            var context=request.context();
            Map<String,String> expected=Map.ofEntries(
                Map.entry("schema","elmos.deployment.independent-evidence.v1"),
                Map.entry("tenantId",context.tenantId().toString()),Map.entry("accountId",context.accountId().toString()),
                Map.entry("projectId",context.projectId().toString()),Map.entry("jobId",context.jobId().toString()),
                Map.entry("stageId",context.stageId().toString()),Map.entry("workItemId",context.workItemId().toString()),
                Map.entry("attemptId",context.attemptId().toString()),Map.entry("tool",context.tool()),
                Map.entry("idempotencyKey",context.idempotencyKey()),Map.entry("requestHash",context.requestHash()),
                Map.entry("invocation",invocation),Map.entry("artifactId",artifactId.toString()),
                Map.entry("artifactDigest",binding.artifact().compact()),Map.entry("producer",binding.producer()),
                Map.entry("verifier",verifier.principal()),Map.entry("decision","PASS"));
            check(body.isObject() && body.size() == expected.size()+2);
            for (var field:expected.entrySet()) {
                check(body.path(field.getKey()).isTextual() && field.getValue().equals(body.path(field.getKey()).textValue()));
            }
            check(body.path("issuedAt").isIntegralNumber() && body.path("issuedAt").canConvertToLong()
                    && body.path("expiresAt").isIntegralNumber() && body.path("expiresAt").canConvertToLong());
            long now=clock.instant().getEpochSecond(), issued=body.path("issuedAt").longValue(), expires=body.path("expiresAt").longValue();
            check(issued >= 0 && issued <= now && now-issued <= 300 && expires > now && expires-issued <= 300);
            check(verifier.equals(trust.requireCurrent(binding.verifierKeyId())));
        } catch (Exception invalid) {
            throw new SecurityException("DEPLOYMENT_INDEPENDENT_EVIDENCE_REJECTED");
        }
    }

    private static void check(boolean condition) { if (!condition) throw new SecurityException(); }
}
