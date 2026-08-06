package io.elmos.architecture;

import java.nio.file.Files;
import java.nio.file.Path;

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
     * Abort the calling test when {@code relativePath} is absent, otherwise return it.
     *
     * @param root         repository root
     * @param relativePath bundle-relative file the caller is about to read
     * @return the resolved path, guaranteed to exist when this method returns
     */
    static Path required(Path root, String relativePath) {
        Path resolved = root.resolve(relativePath);
        assumeTrue(
                Files.isRegularFile(resolved),
                "SOURCE_PACKAGE_ABSENT=" + relativePath
                        + " reason=missing — optional canonical Skill import bundle is not part of a"
                        + " normal source checkout; bundle-bound assertions skipped, the tracked"
                        + " installed distribution is validated separately");
        return resolved;
    }
}
