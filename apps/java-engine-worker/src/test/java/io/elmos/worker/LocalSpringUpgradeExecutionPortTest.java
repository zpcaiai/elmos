package io.elmos.worker;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.util.EnumSet;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class LocalSpringUpgradeExecutionPortTest {
    @TempDir Path temporaryDirectory;

    @Test void readOnlySeedBecomesWritableOnlyInsideThePerRunRepository() throws Exception {
        Path seed = temporaryDirectory.resolve("seed");
        Path seedArtifact = seed.resolve("org/example/library/1.0/library-1.0.jar");
        Path seedTracking = seedArtifact.getParent().resolve("_remote.repositories");
        Files.createDirectories(seedArtifact.getParent());
        Files.writeString(seedArtifact, "artifact");
        Files.writeString(seedTracking, "tracking");
        makeReadOnly(seed);

        Path perRunRepository = temporaryDirectory.resolve("run/.m2/repository");
        LocalSpringUpgradeExecutionPort.copyDependencySeed(seed, perRunRepository);

        assertEquals("artifact", Files.readString(
                perRunRepository.resolve("org/example/library/1.0/library-1.0.jar")));
        assertTrue(Files.isWritable(
                perRunRepository.resolve("org/example/library/1.0/_remote.repositories")));
        assertTrue(Files.isWritable(
                perRunRepository.resolve("org/example/library/1.0")));
        assertTrue(!Files.isWritable(seedTracking) || !ownerCanWrite(seedTracking));
    }

    @Test void securedAndMissingRoutesProveStartupButServerErrorsDoNot() {
        assertTrue(LocalSpringUpgradeExecutionPort.isStartupStatus(200));
        assertTrue(LocalSpringUpgradeExecutionPort.isStartupStatus(401));
        assertTrue(LocalSpringUpgradeExecutionPort.isStartupStatus(403));
        assertTrue(LocalSpringUpgradeExecutionPort.isStartupStatus(404));
        assertFalse(LocalSpringUpgradeExecutionPort.isStartupStatus(199));
        assertFalse(LocalSpringUpgradeExecutionPort.isStartupStatus(500));
    }

    private static void makeReadOnly(Path root) throws Exception {
        try (var paths = Files.walk(root)) {
            for (Path path : paths.sorted(java.util.Comparator.reverseOrder()).toList()) {
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
