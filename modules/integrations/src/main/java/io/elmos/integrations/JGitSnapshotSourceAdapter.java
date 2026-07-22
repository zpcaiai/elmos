package io.elmos.integrations;

import io.elmos.scm.EphemeralCredential;
import io.elmos.snapshot.SnapshotPorts;
import org.eclipse.jgit.api.Git;
import org.eclipse.jgit.lib.Ref;
import org.eclipse.jgit.revwalk.RevWalk;
import org.eclipse.jgit.transport.RefSpec;
import org.eclipse.jgit.transport.UsernamePasswordCredentialsProvider;

import java.io.IOException;
import java.net.URI;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.*;

public final class JGitSnapshotSourceAdapter implements SnapshotPorts.RefResolver, SnapshotPorts.SourceFetcher {
    public interface RepositoryLocationResolver { URI cloneUri(String repositoryId); }
    private final RepositoryLocationResolver locations; private final Path stagingRoot;

    public JGitSnapshotSourceAdapter(RepositoryLocationResolver locations, Path stagingRoot) {
        this.locations = Objects.requireNonNull(locations); this.stagingRoot = Objects.requireNonNull(stagingRoot).toAbsolutePath().normalize();
        try { Files.createDirectories(this.stagingRoot); }
        catch (IOException error) { throw new IllegalArgumentException("snapshot staging root is unavailable", error); }
    }

    @Override public SnapshotPorts.ResolvedRef resolve(String repositoryId, String requestedRef, EphemeralCredential credential) {
        validateRef(requestedRef); URI uri = requireLocation(repositoryId);
        if (requestedRef.matches("[0-9a-f]{40}")) return new SnapshotPorts.ResolvedRef(requestedRef, null, requestedRef);
        return withCredential(credential, password -> {
            try {
                Collection<Ref> advertised = Git.lsRemoteRepository().setRemote(uri.toString()).setHeads(true).setTags(true)
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

    @Override public SnapshotPorts.FetchedSource fetch(String repositoryId, SnapshotPorts.ResolvedRef ref, EphemeralCredential credential) {
        if (ref == null || ref.commitSha() == null || !ref.commitSha().matches("[0-9a-f]{40}")) throw new IllegalArgumentException("immutable commit is required");
        URI uri = requireLocation(repositoryId); Path staging;
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
                    .setCredentialsProvider(new UsernamePasswordCredentialsProvider("x-access-token", password)).call();
            var fetched = git.getRepository().resolve("refs/elmos/snapshot^{commit}");
            if (fetched == null || !fetched.name().equals(ref.commitSha())) throw new SecurityException("fetched commit differs from resolved immutable SHA");
            git.checkout().setName(ref.commitSha()).setForced(true).call();
            try (RevWalk walk = new RevWalk(git.getRepository())) { return walk.parseCommit(fetched).getTree().getId().name(); }
        } catch (RuntimeException error) { throw error; }
        catch (Exception error) { throw new IllegalStateException("SCM_SOURCE_FETCH_FAILED", error); }
    }
    private URI requireLocation(String repositoryId) {
        URI uri = locations.cloneUri(repositoryId);
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
