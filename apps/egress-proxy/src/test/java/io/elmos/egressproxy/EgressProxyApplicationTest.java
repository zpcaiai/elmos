package io.elmos.egressproxy;

import org.junit.jupiter.api.Test;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;

import static org.junit.jupiter.api.Assertions.*;

class EgressProxyApplicationTest {
    @Test void acceptsOnlyExactDnsConnectTo443() throws Exception {
        var request=EgressProxyApplication.ConnectRequest.read(new ByteArrayInputStream("CONNECT repo.maven.apache.org:443 HTTP/1.1\r\nHost: repo.maven.apache.org\r\n\r\n".getBytes(StandardCharsets.US_ASCII)));
        assertEquals("repo.maven.apache.org",request.host());
        assertThrows(EgressProxyApplication.ProxyRejectedException.class,()->EgressProxyApplication.ConnectRequest.read(new ByteArrayInputStream("GET https://example.com/ HTTP/1.1\r\n\r\n".getBytes(StandardCharsets.US_ASCII))));
        assertThrows(EgressProxyApplication.ProxyRejectedException.class,()->EgressProxyApplication.ConnectRequest.read(new ByteArrayInputStream("CONNECT 169.254.169.254:443 HTTP/1.1\r\n\r\n".getBytes(StandardCharsets.US_ASCII))));
        assertThrows(EgressProxyApplication.ProxyRejectedException.class,()->EgressProxyApplication.ConnectRequest.read(new ByteArrayInputStream("CONNECT example.com:80 HTTP/1.1\r\n\r\n".getBytes(StandardCharsets.US_ASCII))));
    }
}
