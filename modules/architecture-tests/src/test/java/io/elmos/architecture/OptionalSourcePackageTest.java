package io.elmos.architecture;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.opentest4j.TestAbortedException;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OptionalSourcePackageTest {

    @TempDir
    Path root;

    @Test
    void absentBundleIsReportedAsAnExplicitSkip() {
        TestAbortedException error = assertThrows(
                TestAbortedException.class,
                () -> OptionalSourcePackage.required(root, "optional-bundle/manifest.json"));

        assertTrue(error.getMessage().contains("SOURCE_PACKAGE_ABSENT="));
    }

    @Test
    void presentButIncompleteBundleFailsClosed() throws IOException {
        Files.createDirectory(root.resolve("optional-bundle"));

        AssertionError error = assertThrows(
                AssertionError.class,
                () -> OptionalSourcePackage.required(root, "optional-bundle/manifest.json"));

        assertTrue(error.getMessage().contains("SOURCE_PACKAGE_INCOMPLETE="));
    }

    @Test
    void presentBundleReturnsOnlyItsRequiredRegularFile() throws IOException {
        Path bundle = Files.createDirectory(root.resolve("optional-bundle"));
        Path manifest = Files.writeString(bundle.resolve("manifest.json"), "{}\n");

        assertEquals(manifest, OptionalSourcePackage.required(root, "optional-bundle/manifest.json"));
    }

    @Test
    void pathTraversalIsRejectedBeforeFilesystemAccess() {
        assertThrows(
                IllegalArgumentException.class,
                () -> OptionalSourcePackage.required(root, "../outside/manifest.json"));
    }

    @Test
    void intermediateDirectorySymlinkCannotEscapeTheBundle() throws IOException {
        Path bundle = Files.createDirectory(root.resolve("optional-bundle"));
        Path outside = Files.createDirectory(root.resolve("outside"));
        Files.writeString(outside.resolve("provenance.md"), "untrusted\n");
        Files.createSymbolicLink(bundle.resolve("references"), Path.of("..", "outside"));

        AssertionError error = assertThrows(
                AssertionError.class,
                () -> OptionalSourcePackage.required(
                        root, "optional-bundle/references/provenance.md"));

        assertTrue(error.getMessage().contains("parent-missing-or-not-a-real-directory"));
    }
}
