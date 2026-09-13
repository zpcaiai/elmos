package io.elmos.liveworkbench;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.product.execution.SecureExecutionAdmissionService;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtDecoders;
import org.springframework.transaction.support.TransactionTemplate;

import java.net.URI;
import java.net.http.HttpClient;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.time.Clock;
import java.time.Duration;

@Configuration
public class LiveWorkbenchConfiguration {
    @Bean Clock liveWorkbenchClock() { return Clock.systemUTC(); }

    @Bean LiveWorkbenchStore liveWorkbenchStore(JdbcTemplate jdbc, TransactionTemplate transactions, ObjectMapper json) {
        return new JdbcLiveWorkbenchStore(jdbc, transactions, json);
    }

    @Bean LiveWorkbenchCatalogStore liveWorkbenchCatalogStore(JdbcTemplate jdbc, TransactionTemplate transactions, ObjectMapper json) {
        return new JdbcLiveWorkbenchCatalogStore(jdbc, transactions, json);
    }

    @Bean SecureExecutionAdmissionService secureExecutionAdmissionService() {
        return new SecureExecutionAdmissionService();
    }

    @Bean SandboxProviderPort sandboxProviderPort(ObjectMapper json,
            @Value("${elmos.live-workbench.provider.base-uri:}") String baseUri,
            @Value("${elmos.live-workbench.provider.signing-key:}") String signingKeyInline,
            @Value("${elmos.live-workbench.provider.signing-key-file:}") String signingKeyFile,
            @Value("${elmos.live-workbench.provider.timeout-seconds:10}") long timeoutSeconds,
            @Value("${elmos.live-workbench.provider.allow-loopback-http:false}") boolean allowLoopbackHttp,
            @Value("${elmos.live-workbench.provider.preview-origins:}") String previewOrigins) {
        if (baseUri.isBlank() || (signingKeyFile.isBlank() && signingKeyInline.isBlank())) return new FailClosedSandboxProvider();
        String signingKey = !signingKeyInline.isBlank() ? signingKeyInline : readSecret(signingKeyFile);
        Duration timeout = Duration.ofSeconds(timeoutSeconds);
        return new HttpSandboxProvider(HttpClient.newBuilder().connectTimeout(timeout).build(), json,
                new HttpSandboxProvider.Configuration(URI.create(baseUri), timeout, signingKey, allowLoopbackHttp,
                        java.util.Arrays.stream(previewOrigins.split(",")).map(String::trim).filter(value -> !value.isEmpty())
                                .collect(java.util.stream.Collectors.toUnmodifiableSet())));
    }

    private static String readSecret(String value) {
        try {
            Path path = Path.of(value);
            if (!path.isAbsolute() || Files.isSymbolicLink(path) || !Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)
                    || Files.size(path) < 32 || Files.size(path) > 4_096)
                throw new IllegalStateException("sandbox provider signing-key file is invalid");
            try {
                var permissions = Files.getPosixFilePermissions(path, LinkOption.NOFOLLOW_LINKS);
                if (permissions.contains(PosixFilePermission.GROUP_WRITE) || permissions.contains(PosixFilePermission.OTHERS_WRITE)
                        || permissions.contains(PosixFilePermission.OTHERS_READ))
                    throw new IllegalStateException("sandbox provider signing-key file permissions are too broad");
            } catch (UnsupportedOperationException ignored) { /* non-POSIX hosts rely on their native ACLs */ }
            String secret = Files.readString(path).trim();
            if (secret.length() < 32) throw new IllegalStateException("sandbox provider signing key is too short");
            return secret;
        } catch (java.io.IOException error) {
            throw new IllegalStateException("sandbox provider signing-key file is unavailable", error);
        }
    }

    @Bean ProductionLiveWorkbenchService productionLiveWorkbenchService(LiveWorkbenchStore store, LiveWorkbenchCatalogStore catalog,
            SandboxProviderPort provider, SecureExecutionAdmissionService admission, Clock clock) {
        return new ProductionLiveWorkbenchService(store, catalog, provider, admission, clock);
    }

    @Bean ProductionLiveWorkbenchKnowledgeService productionLiveWorkbenchKnowledgeService(LiveWorkbenchCatalogStore catalog,
            LiveWorkbenchStore store, SandboxProviderPort provider, Clock clock) {
        return new ProductionLiveWorkbenchKnowledgeService(catalog, store, provider, clock);
    }

    @Bean JwtDecoder liveWorkbenchJwtDecoder(@Value("${elmos.live-workbench.oidc-issuer-uri}") String issuerUri) {
        if (issuerUri == null || issuerUri.isBlank()) throw new IllegalStateException("ELMOS_OIDC_ISSUER_URI is required");
        return JwtDecoders.fromIssuerLocation(issuerUri);
    }
}
