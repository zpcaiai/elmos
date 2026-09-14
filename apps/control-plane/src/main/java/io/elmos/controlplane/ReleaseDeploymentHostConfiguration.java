package io.elmos.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.security.KeyFactory;
import java.security.spec.PKCS8EncodedKeySpec;
import java.time.Clock;
import java.time.Duration;
import java.util.Base64;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

@Configuration
class ReleaseDeploymentHostConfiguration {
    record ConfigurationFile(String endpoint, String audience, String keyId,
                             Map<String, ReleaseDeploymentController.Binding> environments) {}

    @Bean
    @ConditionalOnProperty(name = "elmos.release-deployment.enabled", havingValue = "true")
    ReleaseDeploymentController.Host releaseDeploymentHost(
            @Value("${elmos.release-deployment.configuration-file}") Path configuration,
            @Value("${elmos.release-deployment.signing-key-file}") Path signingKey,
            ObjectMapper json) throws Exception {
        var config = json.readValue(readOwned(configuration, 262144), ConfigurationFile.class);
        URI base = URI.create(config.endpoint());
        if (!"https".equals(base.getScheme()) || base.getHost() == null || base.getUserInfo() != null
                || base.getQuery() != null || base.getFragment() != null
                || !(base.getPath().isEmpty() || base.getPath().equals("/"))) {
            throw new IllegalArgumentException("DEPLOYMENT_HTTPS_ENDPOINT_REQUIRED");
        }
        var key = KeyFactory.getInstance("Ed25519").generatePrivate(new PKCS8EncodedKeySpec(
                Base64.getDecoder().decode(new String(readOwned(signingKey, 4096),
                        java.nio.charset.StandardCharsets.US_ASCII).trim())));
        var signer = new DeploymentHostSigner(config.keyId(), config.audience(), key, Clock.systemUTC(), json);
        return new HttpHost(base, Map.copyOf(config.environments()), signer, json);
    }

    static byte[] readOwned(Path path, int bound) throws Exception {
        Path absolute = path.toAbsolutePath().normalize();
        for (Path part = absolute; part != null; part = part.getParent()) {
            if (Files.isSymbolicLink(part)) throw new IllegalArgumentException("DEPLOYMENT_TRUST_SYMLINK");
        }
        if (!Files.isRegularFile(absolute, LinkOption.NOFOLLOW_LINKS) || Files.size(absolute) > bound) {
            throw new IllegalArgumentException("DEPLOYMENT_TRUST_FILE_INVALID");
        }
        if (Files.getFileStore(absolute).supportsFileAttributeView("posix")) {
            var permissions = Files.getPosixFilePermissions(absolute, LinkOption.NOFOLLOW_LINKS);
            if (permissions.stream().anyMatch(p -> p.name().startsWith("GROUP_") || p.name().startsWith("OTHERS_"))) {
                throw new IllegalArgumentException("DEPLOYMENT_TRUST_OWNER_ONLY");
            }
        } else {
            var acl = Files.getFileAttributeView(absolute,
                    java.nio.file.attribute.AclFileAttributeView.class, LinkOption.NOFOLLOW_LINKS);
            if (acl == null) throw new IllegalArgumentException("DEPLOYMENT_TRUST_ACL_UNAVAILABLE");
            var owner = acl.getOwner();
            for (var entry : acl.getAcl()) {
                String name = entry.principal().getName();
                boolean system = name.equalsIgnoreCase("NT AUTHORITY\\SYSTEM")
                        || name.equalsIgnoreCase("BUILTIN\\Administrators");
                if (entry.type() == java.nio.file.attribute.AclEntryType.ALLOW
                        && !entry.principal().equals(owner) && !system && !entry.permissions().isEmpty()) {
                    throw new IllegalArgumentException("DEPLOYMENT_TRUST_OWNER_ONLY");
                }
            }
        }
        byte[] bytes;
        try (var stream = Files.newInputStream(absolute, LinkOption.NOFOLLOW_LINKS)) {
            bytes = stream.readNBytes(bound + 1);
        }
        if (bytes.length > bound) throw new IllegalArgumentException("DEPLOYMENT_TRUST_FILE_BOUNDS");
        return bytes;
    }

    static final class HttpHost implements ReleaseDeploymentController.Host {
        private final URI base;
        private final Map<String, ReleaseDeploymentController.Binding> bindings;
        private final DeploymentHostSigner signer;
        private final ObjectMapper json;
        private final HttpClient client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NEVER).build();

        HttpHost(URI base, Map<String, ReleaseDeploymentController.Binding> bindings,
                 DeploymentHostSigner signer, ObjectMapper json) {
            this.base = base;
            this.bindings = Map.copyOf(bindings);
            this.signer = signer;
            this.json = json;
        }

        public ReleaseDeploymentController.Binding binding(String environment) { return bindings.get(environment); }

        public byte[] exchange(String method, String path, byte[] body, String actor,
                               ReleaseDeploymentController.Binding binding) {
            try {
                String token = signer.sign(method, path, body, actor, binding.scope(), binding.actorPermissions().get(actor));
                var request = HttpRequest.newBuilder(base.resolve(path)).timeout(Duration.ofSeconds(30))
                        .header("Content-Type", "application/json").header("Accept-Encoding", "identity")
                        .header("X-ELMOS-Host-Auth", token)
                        .method(method, HttpRequest.BodyPublishers.ofByteArray(body)).build();
                var response = client.send(request, HttpResponse.BodyHandlers.ofInputStream());
                try (var stream = response.body()) {
                    if (response.statusCode() != 200) {
                        throw new ResponseStatusException(response.statusCode() == 403 ? HttpStatus.FORBIDDEN
                                : HttpStatus.BAD_GATEWAY, "DEPLOYMENT_WORKER_REJECTED");
                    }
                    if (!response.headers().firstValue("Content-Type").orElse("").split(";", 2)[0]
                            .equals("application/json") || !response.headers().firstValue("Content-Encoding")
                            .orElse("identity").equals("identity")) {
                        throw new IllegalStateException("DEPLOYMENT_RESPONSE_ENCODING");
                    }
                    // Bound body time as well as header time; input-stream handlers alone do not do this.
                    var read = new java.util.concurrent.FutureTask<byte[]>(() -> stream.readNBytes(1048577));
                    Thread.ofVirtual().start(read);
                    byte[] bytes;
                    try { bytes = read.get(30, java.util.concurrent.TimeUnit.SECONDS); }
                    finally { read.cancel(true); }
                    if (bytes.length > 1048576 || !json.readTree(bytes).isContainerNode()) {
                        throw new IllegalStateException("DEPLOYMENT_RESPONSE_BOUNDS");
                    }
                    return bytes;
                }
            } catch (ResponseStatusException error) {
                throw error;
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "DEPLOYMENT_HOST_INTERRUPTED");
            } catch (Exception error) {
                // Unknown dispatch outcomes are not retried here. Workflow idempotency remains authoritative.
                throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "DEPLOYMENT_HOST_UNAVAILABLE");
            }
        }
    }
}
