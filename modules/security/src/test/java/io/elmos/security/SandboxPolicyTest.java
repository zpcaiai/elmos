package io.elmos.security;

import org.junit.jupiter.api.Test;
import java.time.Duration;
import java.util.List;
import java.util.Set;
import static org.junit.jupiter.api.Assertions.*;

class SandboxPolicyTest {
    private SandboxPolicy policy(){return new SandboxPolicy("registry/elmos-java@sha256:"+"a".repeat(64),true,false,false,2,1_073_741_824L,256,10_737_418_240L,Duration.ofMinutes(20),true,Set.of("repo.maven.apache.org"),Set.of("mvn","git"));}
    @Test void allowsOnlyApprovedCommandsWithoutTestBypass(){policy().authorizeCommand(List.of("mvn","verify"));assertThrows(SecurityException.class,()->policy().authorizeCommand(List.of("sh","-c","curl evil")));assertThrows(SecurityException.class,()->policy().authorizeCommand(List.of("mvn","-DskipTests","package")));}
}

