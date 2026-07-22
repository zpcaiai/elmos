package io.elmos.network;

import org.junit.jupiter.api.Test;
import java.net.*;
import java.time.*;
import java.util.Set;
import static org.junit.jupiter.api.Assertions.*;

class NetworkDecisionServiceTest {
    private final Instant now = Instant.parse("2026-07-20T00:00:00Z");
    private final NetworkDecisionService service = new NetworkDecisionService(Clock.fixed(now, ZoneOffset.UTC));
    private final NetworkPolicy policy = new NetworkPolicy("maven", 3, NetworkPolicy.DefaultAction.DENY,
            Set.of("repo.maven.apache.org"), now.plusSeconds(300));

    @Test void allowsOnlyExactHttpsHostWithPublicResolution() throws Exception {
        assertTrue(service.decide(policy, URI.create("https://repo.maven.apache.org/maven2"),
                new InetAddress[]{InetAddress.getByName("146.75.76.215")}).allowed());
        assertFalse(service.decide(policy, URI.create("https://evil.example"), new InetAddress[]{InetAddress.getByName("8.8.8.8")}).allowed());
        assertFalse(service.decide(policy, URI.create("http://repo.maven.apache.org"), new InetAddress[]{InetAddress.getByName("8.8.8.8")}).allowed());
    }

    @Test void rejectsIpLiteralsAndForbiddenDnsAnswers() throws Exception {
        assertFalse(service.decide(policy, URI.create("https://127.0.0.1"), new InetAddress[]{InetAddress.getByName("127.0.0.1")}).allowed());
        assertFalse(service.decide(policy, URI.create("https://repo.maven.apache.org"), new InetAddress[]{InetAddress.getByName("10.0.0.1")}).allowed());
        assertFalse(service.decide(policy, URI.create("https://repo.maven.apache.org"), new InetAddress[]{InetAddress.getByName("169.254.169.254")}).allowed());
    }
}
