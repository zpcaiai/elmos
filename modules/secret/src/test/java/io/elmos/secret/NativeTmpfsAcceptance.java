package io.elmos.secret;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Map;

/** Explicit Linux acceptance harness. Uses synthetic bytes only; never a cloud secret. */
public final class NativeTmpfsAcceptance {
    private static void rejected(Runnable action) {
        try { action.run(); }
        catch (SecurityException expected) { return; }
        throw new AssertionError("expected rejection");
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory(Path.of("/dev/shm"), "elmos-secret-",
                PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rwx------")));
        Path disk = Files.createTempDirectory("elmos-secret-negative-");
        try (SecretValue secret = new SecretValue("synthetic-qualification".toCharArray())) {
            TmpfsSecretMaterializer materializer = new TmpfsSecretMaterializer(Map.of("workspace", root));
            materializer.materializeReadOnlyTmpfs("workspace", "lease", secret);
            if (!Files.getPosixFilePermissions(root.resolve("lease")).equals(PosixFilePermissions.fromString("r--------"))) {
                throw new AssertionError("file permissions");
            }
            if (!Files.readString(root.resolve("lease")).equals("synthetic-qualification")) throw new AssertionError("bytes");
            rejected(() -> materializer.materializeReadOnlyTmpfs("workspace", "lease", secret));
            rejected(() -> materializer.materializeReadOnlyTmpfs("other", "lease", secret));
            rejected(() -> materializer.materializeReadOnlyTmpfs("workspace", "../escape", secret));
            rejected(() -> new TmpfsSecretMaterializer(Map.of("workspace", disk)));
            Path nested = Files.createDirectory(root.resolve("nested"),
                    PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rwx------")));
            rejected(() -> new TmpfsSecretMaterializer(Map.of("one", root, "two", nested)));
            Files.delete(nested);
            Files.createSymbolicLink(root.resolve("link"), root.resolve("lease"));
            rejected(() -> materializer.materializeReadOnlyTmpfs("workspace", "link", secret));
            Files.delete(root.resolve("link"));
            materializer.remove("workspace", "lease");
            materializer.remove("workspace", "lease");
            if (Files.exists(root.resolve("lease"))) throw new AssertionError("cleanup");
            System.out.println("PASS: real tmpfs bytes/0400, duplicate, scope, traversal, disk, overlap, symlink, idempotent cleanup");
        } finally {
            Files.deleteIfExists(root.resolve("link"));
            Files.deleteIfExists(root.resolve("lease"));
            Files.deleteIfExists(root.resolve("nested"));
            Files.delete(root);
            Files.delete(disk);
        }
    }
}
