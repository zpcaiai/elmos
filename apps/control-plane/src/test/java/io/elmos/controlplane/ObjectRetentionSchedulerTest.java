package io.elmos.controlplane;

import com.sun.net.httpserver.HttpServer;
import io.elmos.persistence.JdbcObjectStorageStore;
import io.elmos.persistence.JdbcTenantObjectRetentionStore;
import io.elmos.storage.S3ObjectStore;
import io.elmos.storage.SigV4Presigner;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import java.net.InetSocketAddress;
import java.time.Clock;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class ObjectRetentionSchedulerTest {
    final JdbcObjectStorageStore metadata=mock(JdbcObjectStorageStore.class);
    final JdbcTenantObjectRetentionStore retention=mock(JdbcTenantObjectRetentionStore.class);
    final String sha="a".repeat(64);

    @Test void hostSchedulerRequiresExplicitEnablement() {
        var condition=ObjectRetentionScheduler.class.getAnnotation(ConditionalOnProperty.class);
        assertNotNull(condition);assertFalse(condition.matchIfMissing());
        assertArrayEquals(new String[]{"host-gc-enabled"},condition.name());
        context().run(c->{assertNull(c.getStartupFailure());assertTrue(c.getBeansOfType(ObjectRetentionScheduler.class).isEmpty());});
        verifyNoInteractions(metadata,retention);
    }

    @Test void enablingUnfencedS3FailsStartupBeforeProviderEffect() throws Exception {
        AtomicInteger calls=new AtomicInteger();
        HttpServer server=server(204,calls,new AtomicReference<>());
        try {
            when(metadata.activeBackend()).thenReturn(backend(server));
            context().withPropertyValues("elmos.object-storage.host-gc-enabled=true").run(c->{
                Throwable failure=c.getStartupFailure();assertNotNull(failure);
                while(failure.getCause()!=null)failure=failure.getCause();
                assertInstanceOf(IllegalStateException.class,failure);
                assertEquals("PHYSICAL_GC_BLOCKED_UPLOAD_FENCING",failure.getMessage());
            });
            assertEquals(S3ObjectStore.HostedPhysicalGcCapability.BLOCKED_UPLOAD_FENCING,
                    S3ObjectStore.hostedPhysicalGcCapability(backend(server)));
            verify(metadata).activeBackend();verifyNoInteractions(retention);
            assertEquals(0,calls.get());
        } finally {server.stop(0);}
    }

    @Test void verifiedWriteOnceBackendAllowsSchedulerConstruction() throws Exception {
        AtomicInteger calls=new AtomicInteger();
        HttpServer server=server(204,calls,new AtomicReference<>());
        try {
            when(metadata.activeBackend()).thenReturn(fencedBackend(server));
            context().withPropertyValues("elmos.object-storage.host-gc-enabled=true")
                    .run(c->{assertNull(c.getStartupFailure());assertEquals(1,
                            c.getBeansOfType(ObjectRetentionScheduler.class).size());});
            assertEquals(S3ObjectStore.HostedPhysicalGcCapability.WRITE_ONCE_RECLAIM_FENCE_V1,
                    S3ObjectStore.hostedPhysicalGcCapability(fencedBackend(server)));
            verify(metadata).activeBackend();verifyNoInteractions(retention);
            assertEquals(0,calls.get());
        } finally {server.stop(0);}
    }

    @ParameterizedTest @ValueSource(strings={"backend","key"})
    void backendOrKeyMismatchNeverReachesProvider(String drift) throws Exception {
        AtomicInteger calls=new AtomicInteger();
        HttpServer server=server(204,calls,new AtomicReference<>());
        try {
            var purge=new JdbcTenantObjectRetentionStore.Purge("run","org-gc","obj",sha,
                    drift.equals("backend")?"other":"primary",drift.equals("key")?"wrong":"org-gc/obj/"+sha);
            assertEquals("OBJECT_GC_PROVIDER_BINDING_MISMATCH",assertThrows(S3ObjectStore.ObjectStorageException.class,
                    ()->ObjectRetentionScheduler.validateBinding(backend(server),purge)).getMessage());
            assertEquals(0,calls.get());
        } finally {server.stop(0);}
    }

    @ParameterizedTest @ValueSource(ints={204,404,500})
    void lowLevelDeleteResultDoesNotByItselfProveHostedGcSafety(int status) throws Exception {
        AtomicInteger calls=new AtomicInteger();AtomicReference<String> request=new AtomicReference<>();
        HttpServer server=server(status,calls,request);
        try {
            var provider=new S3ObjectStore(backend(server),metadata,Clock.systemUTC());
            if(status==500) assertThrows(S3ObjectStore.ObjectStorageException.class,()->provider.deleteObject("org-gc",sha));
            else {provider.deleteObject("org-gc",sha);provider.deleteObject("org-gc",sha);assertEquals(2,calls.get());}
            assertEquals("DELETE /bucket/org-gc/obj/"+sha,request.get());
            assertThrows(IllegalStateException.class,()->S3ObjectStore
                    .hostedPhysicalGcCapability(backend(server))
                    .requireWriterQuiescence());
            verifyNoInteractions(metadata,retention);
        } finally {server.stop(0);}
    }

    ApplicationContextRunner context() {
        return new ApplicationContextRunner().withUserConfiguration(ObjectRetentionScheduler.class)
                .withBean(JdbcObjectStorageStore.class,()->metadata)
                .withBean(JdbcTenantObjectRetentionStore.class,()->retention)
                .withBean(Clock.class,Clock::systemUTC);
    }

    S3ObjectStore.Backend backend(HttpServer server) {
        return new S3ObjectStore.Backend("primary","S3","ACTIVE",
                "http://127.0.0.1:"+server.getAddress().getPort(),
                "bucket","us-east-1",true,"NONE",null,1024,
                S3ObjectStore.LEGACY_UNFENCED,
                SigV4Presigner.Credentials.of("fixture-access","fixture-secret"));
    }
    S3ObjectStore.Backend fencedBackend(HttpServer server) {
        var backend=backend(server);
        return new S3ObjectStore.Backend(backend.backendId(),backend.backendKind(),
                backend.state(),backend.endpoint(),backend.bucket(),backend.region(),
                backend.pathStyle(),backend.serverSideEncryption(),backend.cmkReference(),
                backend.maxObjectBytes(),S3ObjectStore.WRITE_ONCE_RECLAIM_FENCE_V1,
                backend.credentials());
    }
    static HttpServer server(int status,AtomicInteger count,AtomicReference<String> request) throws Exception {
        var server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        server.createContext("/",exchange->{count.incrementAndGet();request.set(exchange.getRequestMethod()+" "+exchange.getRequestURI().getPath());
            exchange.sendResponseHeaders(status,-1);exchange.close();});
        server.start();return server;
    }
}
