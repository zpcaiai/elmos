package io.elmos.integrations;

import java.net.URI;
import java.util.Arrays;
import java.util.Objects;

/** Pins credential-bearing GitHub clones to one configured HTTPS origin and path prefix. */
public final class GitHubCloneUriPolicy {
    private final URI base;
    private final String basePath;

    public GitHubCloneUriPolicy(String baseUrl) {
        this.base = parse(Objects.requireNonNull(baseUrl, "baseUrl"), "clone base URL");
        requireCredentialFreeHttps(base, "clone base URL");
        this.basePath = normalizedBasePath(base);
    }

    public URI requireAllowed(String cloneUrl) {
        URI candidate = parse(cloneUrl, "repository clone URL");
        requireCredentialFreeHttps(candidate, "repository clone URL");
        if (!base.getHost().equalsIgnoreCase(candidate.getHost())
                || effectivePort(base) != effectivePort(candidate)) {
            throw new SecurityException("repository clone URL leaves the configured GitHub origin");
        }
        String path = candidate.getPath();
        if (!Objects.equals(candidate.getRawPath(), path)
                || !path.startsWith(basePath + "/")
                || !path.endsWith(".git")) {
            throw new SecurityException("repository clone URL is outside the configured path");
        }
        String relative = path.substring(basePath.length() + 1);
        String[] segments = relative.split("/", -1);
        if (segments.length != 2
                || Arrays.stream(segments).anyMatch(GitHubCloneUriPolicy::unsafeSegment)
                || !segments[0].matches("[A-Za-z0-9](?:[A-Za-z0-9._-]{0,99})")
                || !segments[1].matches("[A-Za-z0-9](?:[A-Za-z0-9._-]{0,99})\\.git")) {
            throw new SecurityException("repository clone URL has an invalid GitHub repository path");
        }
        return candidate;
    }

    private static URI parse(String value, String field) {
        try {
            return URI.create(value);
        } catch (RuntimeException invalid) {
            throw new SecurityException(field + " is invalid", invalid);
        }
    }

    private static void requireCredentialFreeHttps(URI uri, String field) {
        if (!"https".equals(uri.getScheme())
                || uri.getHost() == null
                || uri.getUserInfo() != null
                || uri.getQuery() != null
                || uri.getFragment() != null) {
            throw new SecurityException(field + " must be credential-free HTTPS");
        }
    }

    private static String normalizedBasePath(URI base) {
        String path = base.getPath();
        if (!Objects.equals(base.getRawPath(), path)) {
            throw new SecurityException("clone base URL path must not be encoded");
        }
        if (path == null || path.isEmpty() || "/".equals(path)) {
            return "";
        }
        String normalized = path.endsWith("/")
                ? path.substring(0, path.length() - 1) : path;
        if (!normalized.startsWith("/")
                || Arrays.stream(normalized.substring(1).split("/", -1))
                        .anyMatch(GitHubCloneUriPolicy::unsafeSegment)) {
            throw new SecurityException("clone base URL path is invalid");
        }
        return normalized;
    }

    private static boolean unsafeSegment(String segment) {
        return segment.isEmpty() || ".".equals(segment) || "..".equals(segment);
    }

    private static int effectivePort(URI uri) {
        return uri.getPort() < 0 ? 443 : uri.getPort();
    }
}
