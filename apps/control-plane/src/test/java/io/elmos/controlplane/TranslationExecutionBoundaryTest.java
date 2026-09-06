package io.elmos.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.integrations.GitRepositoryWorkspaceService;
import io.elmos.persistence.JdbcObjectStorageStore;
import io.elmos.workflow.ExecutionJobPort;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class TranslationExecutionBoundaryTest {
    @Test void inputDownloadAdmissionIsHeldUntilTheActualStreamFinishes() throws Exception {
        var entered=new java.util.concurrent.CountDownLatch(1);var release=new java.util.concurrent.CountDownLatch(1);
        var server=com.sun.net.httpserver.HttpServer.create(new java.net.InetSocketAddress("127.0.0.1",0),0);
        server.createContext("/input",exchange->{
            try {
                entered.countDown();
                if(!release.await(20,java.util.concurrent.TimeUnit.SECONDS))throw new java.io.IOException("fixture timed out");
                exchange.sendResponseHeaders(200,100);exchange.getResponseBody().write(new byte[100]);
            } catch(InterruptedException error){Thread.currentThread().interrupt();throw new java.io.IOException(error);}
            finally {exchange.close();}
        });server.start();
        try(var pool=java.util.concurrent.Executors.newSingleThreadExecutor()) {
            var storage=mock(JdbcObjectStorageStore.class);var jobs=mock(ExecutionJobPort.class);
            var stores=mock(ArtifactController.ObjectStoreFactory.class);var store=mock(io.elmos.storage.S3ObjectStore.class);
            when(stores.current()).thenReturn(store);
            when(storage.leaseOwnsJob(anyString(),anyString(),anyString(),anyString())).thenReturn(true);
            when(storage.organizationForLease("lease")).thenReturn(java.util.Optional.of("tenant-fixture"));
            var job=mock(ExecutionJobPort.JobView.class);
            when(job.businessLine()).thenReturn(ExecutionJobPort.BusinessLine.TRANSLATION);when(job.jobKind()).thenReturn(TranslationExecutionPreparation.KIND);
            when(jobs.find("tenant-fixture","job")).thenReturn(java.util.Optional.of(job));
            when(jobs.requestPayload("tenant-fixture","job")).thenReturn(java.util.Optional.of(Map.of("input",Map.of("sha256","a".repeat(64),"byteSize",100,"bindingId","binding","objectId","object"))));
            when(storage.executionInputAvailable("tenant-fixture","job","binding","object","a".repeat(64),100)).thenReturn(true);
            when(store.presignDownload(anyString(),anyString(),anyString(),any())).thenReturn(new io.elmos.storage.S3ObjectStore.DownloadTicket(
                    java.net.URI.create("http://127.0.0.1:"+server.getAddress().getPort()+"/input"),"fixture",java.time.Duration.ofMinutes(1)));
            var controller=new TranslationExecutionInputController(storage,jobs,stores);
            var body=controller.input("lease",new TranslationExecutionInputController.Request("job","runner"),"token").getBody();
            assertNotNull(body);
            var first=pool.submit(()->{var output=new java.io.ByteArrayOutputStream();body.writeTo(output);return output.size();});
            assertTrue(entered.await(20,java.util.concurrent.TimeUnit.SECONDS));
            assertTrue(assertThrows(java.io.IOException.class,()->body.writeTo(new java.io.ByteArrayOutputStream()))
                    .getMessage().contains("LEASE_CAPACITY_EXCEEDED"));
            release.countDown();assertEquals(100,first.get(20,java.util.concurrent.TimeUnit.SECONDS));
            var output=new java.io.ByteArrayOutputStream();body.writeTo(output);assertEquals(100,output.size());
        } finally {release.countDown();server.stop(0);}
    }
    @Test void terminalIdempotentReplayPerformsNoSecondInputPut() {
        replay("actor-fixture",false);
    }
    @Test void anotherActorCannotReplayThePreparedInputAuthority() {
        replay("another-actor",true);
    }
    private static void replay(String existingActor,boolean rejected) {
        var principal=principal(Set.of("translation:execute","repository:read"));
        var attributes=new org.springframework.web.context.request.ServletRequestAttributes(new org.springframework.mock.web.MockHttpServletRequest());
        attributes.setAttribute(OidcTenantMembershipFilter.PRINCIPAL_ATTRIBUTE,principal,org.springframework.web.context.request.RequestAttributes.SCOPE_REQUEST);
        org.springframework.web.context.request.RequestContextHolder.setRequestAttributes(attributes);
        try {
            var jobs=mock(ExecutionJobPort.class);var preparation=mock(TranslationExecutionPreparation.class);
            var existing=mock(ExecutionJobPort.JobView.class);
            when(existing.jobId()).thenReturn("job-existing");when(existing.actorId()).thenReturn(existingActor);
            when(existing.businessLine()).thenReturn(ExecutionJobPort.BusinessLine.TRANSLATION);
            when(existing.jobKind()).thenReturn(TranslationExecutionPreparation.KIND);when(existing.status()).thenReturn(ExecutionJobPort.Status.CANCELLED);
            Map<String,Object> payload=Map.of("repositoryWorkspaceId","workspace","casesBundleId","cases","sourceLanguage","python","targetLanguage","typescript");
            when(jobs.findByIdempotencyKey("tenant-fixture","intent")).thenReturn(java.util.Optional.of(
                    new ExecutionJobPort.IdempotencyLookup("job-existing","a".repeat(64),ExecutionJobPort.Status.CANCELLED)));
            when(jobs.find("tenant-fixture","job-existing")).thenReturn(java.util.Optional.of(existing));
            when(jobs.requestPayload("tenant-fixture","job-existing")).thenReturn(java.util.Optional.of(payload));
            String image="registry.example.test/translation@sha256:"+"a".repeat(64);
            var controller=new ExecutionJobController(jobs,mock(JdbcObjectStorageStore.class),new ObjectMapper(),image,image,image,image,image);
            controller.translationPreparation(preparation);
            var request=new ExecutionJobController.EnqueueRequest("TRANSLATION",TranslationExecutionPreparation.KIND,"intent",payload,null,null,null);
            if(rejected)assertEquals("ELMOS_EXECUTION_IDEMPOTENCY_CONFLICT",assertThrows(ExecutionJobPort.ExecutionStateException.class,()->controller.enqueue(request)).code());
            else assertEquals(202,controller.enqueue(request).getStatusCode().value());
            verifyNoInteractions(preparation);verify(jobs,never()).enqueue(any());
        } finally {org.springframework.web.context.request.RequestContextHolder.resetRequestAttributes();}
    }
    @Test void rejectedLeaseCannotLookUpInputOrObjectStorage() throws Exception {
        var storage = mock(JdbcObjectStorageStore.class);
        var jobs = mock(ExecutionJobPort.class);
        var stores = mock(ArtifactController.ObjectStoreFactory.class);
        var controller = new TranslationExecutionInputController(storage,jobs,stores);
        assertEquals(403,controller.input("lease",new TranslationExecutionInputController.Request("job","other-runner"),"bad-token").getStatusCode().value());
        verifyNoInteractions(jobs,stores);
        verify(storage,never()).organizationForLease(anyString());
    }

    @Test void billingCannotSilentlySwitchToTheWalletContract() {
        var provider = new org.springframework.beans.factory.support.StaticListableBeanFactory()
                .getBeanProvider(GitRepositoryWorkspaceService.class);
        var stores = mock(ArtifactController.ObjectStoreFactory.class);
        var jdbc = mock(JdbcClient.class);
        var preparation = new TranslationExecutionPreparation(provider,stores,jdbc,
                mock(TransactionTemplate.class),new ObjectMapper(),"","",true);
        var error=assertThrows(ExecutionJobPort.ExecutionStateException.class,
                () -> preparation.prepare(principal(Set.of("translation:execute","repository:read")),Map.of(),"idempotent"));
        assertEquals("TRANSLATION_HOSTED_BILLING_CONTRACT_REQUIRED",error.code());
        verifyNoInteractions(stores,jdbc);
    }

    @Test void identityIsRequiredBeforeAnyPreparationEffect() {
        ObjectProvider<GitRepositoryWorkspaceService> provider = new org.springframework.beans.factory.support.StaticListableBeanFactory()
                .getBeanProvider(GitRepositoryWorkspaceService.class);
        var stores=mock(ArtifactController.ObjectStoreFactory.class);
        var preparation=new TranslationExecutionPreparation(provider,stores,mock(JdbcClient.class),
                mock(TransactionTemplate.class),new ObjectMapper(),"","",false);
        assertThrows(org.springframework.security.access.AccessDeniedException.class,
                () -> preparation.prepare(principal(Set.of("repository:read")),Map.of(),"idempotent"));
        verifyNoInteractions(stores);
    }

    private static ControlPlanePrincipal principal(Set<String> permissions) {
        var grant=new ControlPlanePrincipal.TenantGrant(Set.of(),permissions);
        return new ControlPlanePrincipal("tenant-fixture","actor-fixture",false,Set.of(),permissions,Map.of("tenant-fixture",grant));
    }
}
