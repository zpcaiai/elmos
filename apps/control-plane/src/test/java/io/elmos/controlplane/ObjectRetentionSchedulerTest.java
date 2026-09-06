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

import java.net.InetSocketAddress;
import java.time.Clock;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

class ObjectRetentionSchedulerTest {
    final JdbcObjectStorageStore metadata=mock(JdbcObjectStorageStore.class);
    final JdbcTenantObjectRetentionStore retention=mock(JdbcTenantObjectRetentionStore.class);
    final String sha="a".repeat(64);

    @Test void hostSchedulerRequiresExplicitEnablement() {
        var condition=ObjectRetentionScheduler.class.getAnnotation(ConditionalOnProperty.class);
        assertNotNull(condition);assertFalse(condition.matchIfMissing());
        assertArrayEquals(new String[]{"host-gc-enabled"},condition.name());
    }

    @ParameterizedTest @ValueSource(strings={"backend","key"})
    void backendOrKeyMismatchNeverReachesProvider(String drift) throws Exception {
        AtomicInteger calls=new AtomicInteger();
        HttpServer server=server(204,calls,new AtomicReference<>());
        try {
            when(metadata.activeBackend()).thenReturn(backend(server));
            var purge=new JdbcTenantObjectRetentionStore.Purge("run","org-gc","obj",sha,
                    drift.equals("backend")?"other":"primary",drift.equals("key")?"wrong":"org-gc/obj/"+sha);
            when(retention.collect(any())).thenAnswer(call->{call.<JdbcTenantObjectRetentionStore.ConfirmedDeleter>getArgument(0).delete(purge);return null;});
            assertEquals("OBJECT_GC_PROVIDER_BINDING_MISMATCH",assertThrows(S3ObjectStore.ObjectStorageException.class,
                    ()->new ObjectRetentionScheduler(metadata,retention,Clock.systemUTC()).collect()).getMessage());
            assertEquals(0,calls.get());
        } finally {server.stop(0);}
    }

    @ParameterizedTest @ValueSource(ints={204,404,500})
    void onlyConfirmedProviderResultsReturnNormallyAndBackendIsCapturedOnce(int status) throws Exception {
        AtomicInteger calls=new AtomicInteger();AtomicReference<String> request=new AtomicReference<>();
        HttpServer server=server(status,calls,request);
        try {
            when(metadata.activeBackend()).thenReturn(backend(server));
            var purge=new JdbcTenantObjectRetentionStore.Purge("run","org-gc","obj",sha,"primary","org-gc/obj/"+sha);
            when(retention.collect(any())).thenAnswer(call->{
                var deleter=call.<JdbcTenantObjectRetentionStore.ConfirmedDeleter>getArgument(0);
                deleter.delete(purge);deleter.delete(purge);
                return new JdbcTenantObjectRetentionStore.RoundResult(2,2,0);
            });
            var scheduler=new ObjectRetentionScheduler(metadata,retention,Clock.systemUTC());
            if(status==500) assertThrows(S3ObjectStore.ObjectStorageException.class,scheduler::collect);
            else {scheduler.collect();assertEquals(2,calls.get());}
            assertEquals("DELETE /bucket/org-gc/obj/"+sha,request.get());
            verify(metadata,times(1)).activeBackend();
        } finally {server.stop(0);}
    }

    S3ObjectStore.Backend backend(HttpServer server) {
        return new S3ObjectStore.Backend("primary","ACTIVE","http://127.0.0.1:"+server.getAddress().getPort(),
                "bucket","us-east-1",true,"NONE",null,1024,SigV4Presigner.Credentials.of("fixture-access","fixture-secret"));
    }
    static HttpServer server(int status,AtomicInteger count,AtomicReference<String> request) throws Exception {
        var server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        server.createContext("/",exchange->{count.incrementAndGet();request.set(exchange.getRequestMethod()+" "+exchange.getRequestURI().getPath());
            exchange.sendResponseHeaders(status,-1);exchange.close();});
        server.start();return server;
    }
}
