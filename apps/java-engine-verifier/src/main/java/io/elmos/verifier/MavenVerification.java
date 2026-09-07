package io.elmos.verifier;

import java.nio.file.Path;
import java.util.List;

interface MavenVerification {
    List<String> verify(Path projectRoot, Path logFile);
}
