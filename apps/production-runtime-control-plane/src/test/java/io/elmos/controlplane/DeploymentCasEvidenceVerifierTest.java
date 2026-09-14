package io.elmos.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.cas.CasDigest;
import io.elmos.cas.LocalDiskCasStore;
import io.elmos.cas.TenantCasStore;
import io.elmos.productionruntime.DeploymentToolExecutor;
import io.elmos.productionruntime.ProductionRuntimeModels.ToolCallRequest;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class DeploymentCasEvidenceVerifierTest {
    @TempDir Path root;
    LocalDiskCasStore cas;
    DeploymentToolExecutor.Request request;
    DeploymentCasEvidenceVerifier verifier;
    DeploymentCasEvidenceVerifier.Binding binding;
    KeyPair signing,producer;
    UUID artifactId=UUID.randomUUID();
    Map<String,Object> body;
    CasDigest artifact;
    boolean revoked;

    @BeforeEach void setup() throws Exception {
        cas=new LocalDiskCasStore("deployment-test",root);
        signing=KeyPairGenerator.getInstance("Ed25519").generateKeyPair();
        producer=KeyPairGenerator.getInstance("Ed25519").generateKeyPair();
        UUID id=UUID.randomUUID(); byte[] payload="{}".getBytes(StandardCharsets.UTF_8);
        var c=new ToolCallRequest(id,id,id,id,id,id,id,"release-deployment:iac.apply","operation",
                "sha256:"+CasDigest.of(payload).hex());
        request=new DeploymentToolExecutor.Request(c,"iac.apply",payload);
        artifact=CasDigest.of(payload); cas.put(artifact,payload);
        body=new LinkedHashMap<>();
        body.put("schema","elmos.deployment.independent-evidence.v1");
        for (String key:java.util.List.of("tenantId","accountId","projectId","jobId","stageId","workItemId","attemptId")) {
            body.put(key,id.toString());
        }
        body.putAll(Map.of("tool",c.tool(),"idempotencyKey",c.idempotencyKey(),"requestHash",c.requestHash(),
            "invocation","invocation","artifactId",artifactId.toString(),"artifactDigest",artifact.compact(),
            "producer","executor","verifier","independent","decision","PASS"));
        body.put("issuedAt",1000); body.put("expiresAt",1200);
        verifier=new DeploymentCasEvidenceVerifier(TenantCasStore.global(cas),(r,i,a)->binding,key->{
            if (revoked) throw new SecurityException();
            return new DeploymentCasEvidenceVerifier.Verifier("independent",signing.getPublic());
        },Clock.fixed(Instant.ofEpochSecond(1100),ZoneOffset.UTC));
        sign();
    }

    void sign() throws Exception {
        byte[] statement=new ObjectMapper().writeValueAsBytes(body);
        CasDigest statementId=CasDigest.of(statement); cas.put(statementId,statement);
        Signature signature=Signature.getInstance("Ed25519"); signature.initSign(signing.getPrivate());
        signature.update("elmos.deployment.independent-evidence.v1\n".getBytes(StandardCharsets.UTF_8));
        signature.update(statement);
        binding=new DeploymentCasEvidenceVerifier.Binding(artifact,statementId,"executor",
            "sha256:"+CasDigest.of(producer.getPublic().getEncoded()).hex(),"independent-key",
            Base64.getEncoder().encodeToString(signature.sign()));
    }

    @Test void readsActualDiskCasAndVerifiesExternalSignature() {
        assertDoesNotThrow(()->verifier.require(request,"invocation",artifactId));
    }

    @Test void revokedVerifierNeverPassesPreviouslyValidEvidence() {
        verifier.require(request,"invocation",artifactId); revoked=true;
        assertThrows(SecurityException.class,()->verifier.require(request,"invocation",artifactId));
    }

    @Test void signedWrongScopeUnknownDecisionOrExpiredReceiptRejected() throws Exception {
        for (var entry:Map.<String,Object>of("tenantId",UUID.randomUUID().toString(),"decision","UNKNOWN",
                "expiresAt",1099,"requestHash","sha256:"+"0".repeat(64)).entrySet()) {
            Object original=body.put(entry.getKey(),entry.getValue()); sign();
            assertThrows(SecurityException.class,()->verifier.require(request,"invocation",artifactId));
            body.put(entry.getKey(),original);
        }
    }

    @Test void producerKeyCannotActAsIndependentVerifier() throws Exception {
        producer=signing; sign();
        assertThrows(SecurityException.class,()->verifier.require(request,"invocation",artifactId));
    }

    @Test void invocationOrArtifactSubstitutionRejected() {
        assertThrows(SecurityException.class,()->verifier.require(request,"other",artifactId));
        assertThrows(SecurityException.class,()->verifier.require(request,"invocation",UUID.randomUUID()));
    }
}
