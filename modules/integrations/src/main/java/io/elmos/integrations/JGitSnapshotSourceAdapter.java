package io.elmos.integrations;

import io.elmos.scm.EphemeralCredential;
import io.elmos.snapshot.SnapshotPorts;
import org.eclipse.jgit.api.Git;
import org.eclipse.jgit.lib.Ref;
import org.eclipse.jgit.revwalk.RevWalk;
import org.eclipse.jgit.transport.RefSpec;
import org.eclipse.jgit.transport.TransportHttp;
import org.eclipse.jgit.transport.UsernamePasswordCredentialsProvider;
import org.eclipse.jgit.transport.http.HttpConnection;
import org.eclipse.jgit.transport.http.HttpConnectionFactory;
import org.eclipse.jgit.transport.http.JDKHttpConnectionFactory;

import java.io.IOException;
import java.net.URI;
import java.net.Proxy;
import java.net.URL;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.*;

public final class JGitSnapshotSourceAdapter implements SnapshotPorts.RefResolver, SnapshotPorts.SourceFetcher {
    public interface RepositoryLocationResolver {
        URI cloneUri(String organizationId, String repositoryId);
    }
    private final RepositoryLocationResolver locations; private final Path stagingRoot;

    public JGitSnapshotSourceAdapter(RepositoryLocationResolver locations, Path stagingRoot) {
        this.locations = Objects.requireNonNull(locations); this.stagingRoot = Objects.requireNonNull(stagingRoot).toAbsolutePath().normalize();
        try { Files.createDirectories(this.stagingRoot); }
        catch (IOException error) { throw new IllegalArgumentException("snapshot staging root is unavailable", error); }
    }

    @Override public SnapshotPorts.ResolvedRef resolve(
            SnapshotPorts.ArtifactResourceContext resource,
            String requestedRef,
            EphemeralCredential credential
    ) {
        validateRef(requestedRef); URI uri = requireLocation(resource);
        if (requestedRef.matches("[0-9a-f]{40}")) return new SnapshotPorts.ResolvedRef(requestedRef, null, requestedRef);
        return withCredential(credential, password -> {
            try {
                Collection<Ref> advertised = Git.lsRemoteRepository().setRemote(uri.toString()).setHeads(true).setTags(true)
                        .setTransportConfigCallback(transport -> pinHttpTransport(transport, uri))
                        .setCredentialsProvider(new UsernamePasswordCredentialsProvider("x-access-token", password)).call();
                Map<String, Ref> refs = new HashMap<>(); advertised.forEach(ref -> refs.put(ref.getName(), ref));
                String full = requestedRef.startsWith("refs/") ? requestedRef : refs.containsKey("refs/heads/" + requestedRef)
                        ? "refs/heads/" + requestedRef : "refs/tags/" + requestedRef;
                Ref ref = refs.get(full); if (ref == null) throw new IllegalArgumentException("SCM_REF_NOT_FOUND");
                Ref peeled = refs.get(full + "^{}"); String commit = peeled == null ? ref.getObjectId().name() : peeled.getObjectId().name();
                if (!commit.matches("[0-9a-f]{40}")) throw new SecurityException("SCM ref did not resolve to a full commit SHA");
                return new SnapshotPorts.ResolvedRef(commit, null, full);
            } catch (RuntimeException error) { throw error; }
            catch (Exception error) { throw new IllegalStateException("SCM_REF_RESOLUTION_FAILED", error); }
        });
    }

    @Override public SnapshotPorts.FetchedSource fetch(
            SnapshotPorts.ArtifactResourceContext resource,
            SnapshotPorts.ResolvedRef ref,
            EphemeralCredential credential
    ) {
        if (ref == null || ref.commitSha() == null || !ref.commitSha().matches("[0-9a-f]{40}")) throw new IllegalArgumentException("immutable commit is required");
        URI uri = requireLocation(resource); Path staging;
        try { staging = Files.createTempDirectory(stagingRoot, "snapshot-"); }
        catch (IOException error) { throw new IllegalStateException("SNAPSHOT_STAGING_CREATE_FAILED", error); }
        try {
            String tree = withCredential(credential, password -> fetchExact(uri, staging, ref, password));
            return new SnapshotPorts.FetchedSource(staging, tree, () -> deleteTree(staging));
        } catch (RuntimeException failure) {
            try { deleteTree(staging); } catch (RuntimeException cleanup) { failure.addSuppressed(cleanup); }
            throw failure;
        }
    }

    private static String fetchExact(URI uri, Path staging, SnapshotPorts.ResolvedRef ref, char[] password) {
        try (Git git = Git.init().setDirectory(staging.toFile()).call()) {
            String source = ref.fetchRef() == null ? ref.commitSha() : ref.fetchRef();
            git.fetch().setRemote(uri.toString()).setDepth(1).setRemoveDeletedRefs(false)
                    .setRefSpecs(new RefSpec("+" + source + ":refs/elmos/snapshot"))
                    .setTransportConfigCallback(transport -> pinHttpTransport(transport, uri))
                    .setCredentialsProvider(new UsernamePasswordCredentialsProvider("x-access-token", password)).call();
            var fetched = git.getRepository().resolve("refs/elmos/snapshot^{commit}");
            if (fetched == null || !fetched.name().equals(ref.commitSha())) throw new SecurityException("fetched commit differs from resolved immutable SHA");
            git.checkout().setName(ref.commitSha()).setForced(true).call();
            try (RevWalk walk = new RevWalk(git.getRepository())) { return walk.parseCommit(fetched).getTree().getId().name(); }
        } catch (RuntimeException error) { throw error; }
        catch (Exception error) { throw new IllegalStateException("SCM_SOURCE_FETCH_FAILED", error); }
    }
    private URI requireLocation(SnapshotPorts.ArtifactResourceContext resource) {
        Objects.requireNonNull(resource, "resource");
        URI uri = locations.cloneUri(resource.organizationId(), resource.repositoryId());
        if (uri == null || uri.getScheme() == null || !(uri.getScheme().equals("https") || uri.getScheme().equals("file"))) throw new SecurityException("only HTTPS or controlled file repositories are supported");
        if (uri.getUserInfo() != null) throw new SecurityException("credentials must not be embedded in clone URI");
        return uri;
    }
    private static void validateRef(String ref) {
        if (ref == null || ref.isBlank() || ref.length() > 512 || ref.contains("..") || ref.contains("@{") || ref.startsWith("-")
                || (!ref.matches("[0-9a-f]{40}") && !ref.matches("(?:refs/(?:heads|tags)/)?[A-Za-z0-9._/-]+"))) throw new SecurityException("SCM_REF_INVALID");
    }
    private static <T> T withCredential(EphemeralCredential credential, java.util.function.Function<char[],T> action) {
        return credential.use(action);
    }

    private static void pinHttpTransport(org.eclipse.jgit.transport.Transport transport, URI cloneUri) {
        if (transport instanceof TransportHttp http) {
            http.setHttpConnectionFactory(new PinnedHttpConnectionFactory(cloneUri));
        }
    }

    /** Rejects automatic or JGit-managed redirects outside the exact credential-bearing repo. */
    private static final class PinnedHttpConnectionFactory implements HttpConnectionFactory {
        private final URI cloneUri;
        private final HttpConnectionFactory delegate = new JDKHttpConnectionFactory();

        private PinnedHttpConnectionFactory(URI cloneUri) {
            this.cloneUri = cloneUri;
        }

        @Override public HttpConnection create(URL url) throws IOException {
            requirePinned(url);
            HttpConnection connection = delegate.create(url);
            connection.setInstanceFollowRedirects(false);
            return connection;
        }

        @Override public HttpConnection create(URL url, Proxy proxy) throws IOException {
            requirePinned(url);
            HttpConnection connection = delegate.create(url, proxy);
            connection.setInstanceFollowRedirects(false);
            return connection;
        }

        private void requirePinned(URL url) throws IOException {
            URI target;
            try {
                target = url.toURI();
            } catch (Exception invalid) {
                throw new IOException("SCM transport URL is invalid", invalid);
            }
            String clonePath = cloneUri.getPath();
            boolean allowedQuery = target.getQuery() == null
                    || "service=git-upload-pack".equals(target.getQuery());
            if (!"https".equals(target.getScheme())
                    || target.getHost() == null
                    || !cloneUri.getHost().equalsIgnoreCase(target.getHost())
                    || effectivePort(cloneUri) != effectivePort(target)
                    || target.getUserInfo() != null
                    || target.getFragment() != null
                    || !allowedQuery
                    || !(Objects.equals(clonePath, target.getPath())
                         || target.getPath().startsWith(clonePath + "/"))) {
                throw new IOException("SCM redirect left the pinned repository origin");
            }
        }

        private static int effectivePort(URI uri) {
            return uri.getPort() < 0 ? 443 : uri.getPort();
        }
    }

    private void deleteTree(Path target) {
        Path normalized = target.toAbsolutePath().normalize();
        if (!normalized.startsWith(stagingRoot) || normalized.equals(stagingRoot)) throw new SecurityException("refusing unsafe staging cleanup");
        try {
            Files.walkFileTree(normalized, new SimpleFileVisitor<>() {
                @Override public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) throws IOException { Files.deleteIfExists(file); return FileVisitResult.CONTINUE; }
                @Override public FileVisitResult postVisitDirectory(Path dir, IOException error) throws IOException { if (error != null) throw error; Files.deleteIfExists(dir); return FileVisitResult.CONTINUE; }
            });
        } catch (IOException error) { throw new IllegalStateException("SNAPSHOT_STAGING_CLEANUP_FAILED", error); }
    }
}
