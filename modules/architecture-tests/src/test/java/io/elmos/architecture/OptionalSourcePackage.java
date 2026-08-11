package io.elmos.architecture;

import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

/**
 * Shared rule for the optional canonical Skill import bundles.
 *
 * <p>A normal source checkout intentionally does not contain them; the rule is stated in
 * {@code tooling/validate_batch97_104_installed.py} and in the repository README. Their byte
 * identities live in the tracked {@code docs/*}{@code /installed-manifest.json} files, so a
 * checkout validates the installed distribution rather than the absent bundle.
 *
 * <p>Assertions that read a bundle therefore abort with an explicit reason instead of erroring
 * with {@link java.nio.file.NoSuchFileException}, which says nothing about this repository. The
 * reason carries the same loud, greppable {@code SOURCE_PACKAGE_ABSENT=} marker the Makefile
 * guard prints, so a skipped bundle assertion can never be misread as a passed one.
 *
 * <p>This never relaxes an assertion that does not need a bundle. Callers must keep every
 * bundle-independent assertion outside the assumption so it still runs on a clean checkout.
 */
final class OptionalSourcePackage {

    private OptionalSourcePackage() {
    }

    /**
     * Abort the calling test only when the complete optional bundle is absent.
     * A present but partial bundle is a broken checkout and therefore fails the test.
     *
     * @param root         repository root
     * @param relativePath bundle-relative file the caller is about to read
     * @return the resolved path, guaranteed to exist when this method returns
     */
    static Path required(Path root, String relativePath) {
        Path normalizedRoot = root.toAbsolutePath().normalize();
        Path relative = Path.of(relativePath).normalize();
        if (relative.isAbsolute() || relative.getNameCount() < 2 || relative.startsWith("..")) {
            throw new IllegalArgumentException("optional source path must name a file inside a bundle");
        }

        Path bundleRoot = normalizedRoot.resolve(relative.getName(0)).normalize();
        Path resolved = normalizedRoot.resolve(relative).normalize();
        if (!bundleRoot.startsWith(normalizedRoot) || !resolved.startsWith(bundleRoot)) {
            throw new IllegalArgumentException("optional source path escapes the repository root");
        }

        assumeTrue(
                Files.exists(bundleRoot, LinkOption.NOFOLLOW_LINKS),
                "SOURCE_PACKAGE_ABSENT=" + relativePath
                        + " reason=bundle-missing — optional canonical Skill import bundle is not part of a"
                        + " normal source checkout; bundle-bound assertions skipped, the tracked"
                        + " installed distribution is validated separately");

        assertTrue(
                Files.isDirectory(bundleRoot, LinkOption.NOFOLLOW_LINKS),
                "SOURCE_PACKAGE_INVALID=" + relative.getName(0)
                        + " reason=bundle-root-is-not-a-real-directory");
        Path parent = bundleRoot;
        for (int index = 1; index < relative.getNameCount() - 1; index++) {
            parent = parent.resolve(relative.getName(index));
            assertTrue(
                    Files.isDirectory(parent, LinkOption.NOFOLLOW_LINKS),
                    "SOURCE_PACKAGE_INCOMPLETE=" + relativePath
                            + " reason=parent-missing-or-not-a-real-directory");
        }
        assertTrue(
                Files.isRegularFile(resolved, LinkOption.NOFOLLOW_LINKS),
                "SOURCE_PACKAGE_INCOMPLETE=" + relativePath
                        + " reason=required-file-missing-or-not-regular");
        return resolved;
    }
}
