package io.elmos.productionruntime;

import io.elmos.productionruntime.ProductionRuntimeModels.*;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class DeploymentToolExecutorTest {
    static final class Ledger implements ProductionToolCallPort, DeploymentToolExecutor.ReceiptLookup {
        ToolCallReceipt receipt;
        final UUID id = UUID.randomUUID();
        public ToolCallReceipt find(ToolCallRequest request) { return receipt; }
        public ToolCallReceipt begin(ToolCallRequest request) {
            if (receipt != null) throw new AssertionError("begin must not retry accepted/unknown calls");
            return receipt = new ToolCallReceipt(id, ToolCallStatus.CREATED,null,null);
        }
        public void claimProviderDispatch(UUID tenant, UUID call) {
            assertEquals(ToolCallStatus.CREATED, receipt.status());
            receipt = new ToolCallReceipt(id,ToolCallStatus.UNKNOWN,null,null);
        }
        public void markProviderAccepted(UUID tenant, UUID call, String invocation) {
            receipt = new ToolCallReceipt(id,ToolCallStatus.PROVIDER_ACCEPTED,invocation,null);
        }
        public void markProviderUnknown(UUID tenant, UUID call, String status) {
            receipt = new ToolCallReceipt(id,ToolCallStatus.UNKNOWN,receipt.providerRequestId(),null);
        }
        public void markProviderFailed(UUID tenant, UUID call, String status) {
            receipt = new ToolCallReceipt(id,ToolCallStatus.FAILED,receipt.providerRequestId(),null);
        }
        public void complete(UUID tenant, UUID call, UUID artifact) {
            receipt = new ToolCallReceipt(id,ToolCallStatus.COMPLETE,receipt.providerRequestId(),artifact);
        }
    }

    DeploymentToolExecutor.Request request() throws Exception {
        UUID id=UUID.randomUUID();
        byte[] payload="{}".getBytes(java.nio.charset.StandardCharsets.UTF_8);
        String hash="sha256:"+HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(payload));
        return new DeploymentToolExecutor.Request(new ToolCallRequest(id,id,id,id,id,id,id,
                "release-deployment:traffic.apply","operation",hash),"traffic.apply",payload);
    }

    @Test void lostResponseDoesNotResubmit() throws Exception {
        var ledger=new Ledger();
        int[] sends={0};
        var provider=new DeploymentToolExecutor.Provider() {
            public String submit(DeploymentToolExecutor.Request request) {
                assertEquals(ToolCallStatus.UNKNOWN,ledger.receipt.status());
                sends[0]++;
                throw new IllegalStateException("lost response");
            }
            public UUID verifiedResponseArtifact(DeploymentToolExecutor.Request request,String invocation) {
                throw new AssertionError("no invocation exists");
            }
            public String reconcile(DeploymentToolExecutor.Request request,UUID call) { return null; }
        };
        var executor=new DeploymentToolExecutor(ledger,r->{},(r,i,a)->{},Map.of("traffic.apply",provider),ledger);
        var request=request();
        assertEquals(ToolCallStatus.UNKNOWN,executor.tick(request).status());
        assertEquals(ToolCallStatus.UNKNOWN,executor.tick(request).status());
        assertEquals(1,sends[0]);
    }

    @Test void completionRequiresIndependentArtifactVerification() throws Exception {
        var ledger=new Ledger();
        UUID artifact=UUID.randomUUID();
        var provider=new DeploymentToolExecutor.Provider() {
            public String submit(DeploymentToolExecutor.Request request) { return "invocation"; }
            public UUID verifiedResponseArtifact(DeploymentToolExecutor.Request request,String invocation) { return artifact; }
            public String reconcile(DeploymentToolExecutor.Request request,UUID call) { return null; }
        };
        var rejecting=new DeploymentToolExecutor(ledger,r->{},(r,i,a)->{throw new IllegalStateException("unverified");},
                                                 Map.of("traffic.apply",provider),ledger);
        var request=request();
        assertThrows(IllegalStateException.class,()->rejecting.tick(request));
        assertEquals(ToolCallStatus.PROVIDER_ACCEPTED,ledger.receipt.status());
        var verified=new DeploymentToolExecutor(ledger,r->{},(r,i,a)->assertEquals(artifact,a),
                                                Map.of("traffic.apply",provider),ledger);
        assertEquals(ToolCallStatus.COMPLETE,verified.tick(request).status());
    }

    @Test void bindsActualWorkflowAndExtensionActionsAndRejectsArbitraryTools() throws Exception {
        var original=request();
        var c=original.context();
        for (String action : java.util.List.of("policy.evaluate","identity.lease_ready","migration.apply",
                "health.verify","rollback.plan","runtime.restore","tls.rotate","iac.apply","iac.destroy",
                "gitops.proposal","gitops.reconcile","helm.render")) {
            var context=new ToolCallRequest(c.tenantId(),c.accountId(),c.projectId(),c.jobId(),c.stageId(),
                    c.workItemId(),c.attemptId(),"release-deployment:"+action,c.idempotencyKey(),c.requestHash());
            assertDoesNotThrow(()->new DeploymentToolExecutor.Request(context,action,original.payload()));
        }
        assertThrows(IllegalArgumentException.class,()->new DeploymentToolExecutor.Request(
                c,"arbitrary.shell",original.payload()));
    }
}
