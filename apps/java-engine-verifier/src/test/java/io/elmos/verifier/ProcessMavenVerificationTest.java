package io.elmos.verifier;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.util.Comparator;
import java.util.EnumSet;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ProcessMavenVerificationTest {
    @TempDir Path temporaryDirectory;

    @Test void distinguishesExactVerifierJavaReleasesFromMavenVersionOutput() {
        String java17 = "Apache Maven 3.9.11\nJava version: 17.0.19, vendor: Eclipse Adoptium";
        String java21 = "Apache Maven 3.9.11\nJava version: 21.0.7, vendor: Eclipse Adoptium";
        assertTrue(ProcessMavenVerification.reportsJavaRelease(java17, "17"));
        assertTrue(!ProcessMavenVerification.reportsJavaRelease(java17, "21"));
        assertTrue(ProcessMavenVerification.reportsJavaRelease(java21, "21"));
    }

    @Test void immutableCacheIsCopiedIntoAWritableVerifierPrivateRepository() throws Exception {
        Path cache = temporaryDirectory.resolve("cache");
        Path artifact = cache.resolve("org/example/library/1.0/library-1.0.jar");
        Path tracking = artifact.getParent().resolve("_remote.repositories");
        Files.createDirectories(artifact.getParent());
        Files.writeString(artifact, "artifact");
        Files.writeString(tracking, "tracking");
        makeReadOnly(cache);

        Path privateRepository = temporaryDirectory.resolve("decision/maven-home/.m2/repository");
        ProcessMavenVerification.copyDependencyCache(cache, privateRepository);

        assertEquals("artifact", Files.readString(
                privateRepository.resolve("org/example/library/1.0/library-1.0.jar")));
        assertTrue(Files.isWritable(
                privateRepository.resolve("org/example/library/1.0/_remote.repositories")));
        assertTrue(!Files.isWritable(tracking) || !ownerCanWrite(tracking));
    }

    private static void makeReadOnly(Path root) throws Exception {
        try (var paths = Files.walk(root)) {
            for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                Set<PosixFilePermission> permissions =
                        EnumSet.copyOf(Files.getPosixFilePermissions(path));
                permissions.remove(PosixFilePermission.OWNER_WRITE);
                permissions.remove(PosixFilePermission.GROUP_WRITE);
                permissions.remove(PosixFilePermission.OTHERS_WRITE);
                Files.setPosixFilePermissions(path, permissions);
            }
        }
    }

    private static boolean ownerCanWrite(Path path) throws Exception {
        return Files.getPosixFilePermissions(path).contains(PosixFilePermission.OWNER_WRITE);
    }
}
