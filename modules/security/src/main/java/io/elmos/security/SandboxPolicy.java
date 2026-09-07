package io.elmos.security;

import java.time.Duration;
import java.util.List;
import java.util.Set;

public record SandboxPolicy(String imageDigest, boolean runAsNonRoot, boolean privileged,
                            boolean hostDockerSocketMounted, int cpuLimit, long memoryBytes,
                            int pidLimit, long diskBytes, Duration timeout, boolean defaultDenyNetwork,
                            Set<String> allowedHosts, Set<String> allowedCommands) {
    public SandboxPolicy {
        if (imageDigest == null || !imageDigest.matches(".+@sha256:[0-9a-f]{64}")) throw new IllegalArgumentException("sandbox image must be pinned by digest");
        if (!runAsNonRoot || privileged || hostDockerSocketMounted) throw new IllegalArgumentException("unsafe sandbox privilege settings");
        if (cpuLimit < 1 || memoryBytes < 268_435_456L || pidLimit < 1 || diskBytes < 1_073_741_824L || timeout == null || timeout.isNegative() || timeout.isZero()) throw new IllegalArgumentException("invalid resource limits");
        if (!defaultDenyNetwork) throw new IllegalArgumentException("network policy must default deny");
        allowedHosts=Set.copyOf(allowedHosts==null?Set.of():allowedHosts); allowedCommands=Set.copyOf(allowedCommands==null?Set.of():allowedCommands);
    }
    public void authorizeCommand(List<String> command) {
        if (command == null || command.isEmpty() || !allowedCommands.contains(command.getFirst())) throw new SecurityException("command is not allowed");
        if (command.stream().anyMatch(v -> v.equals("-DskipTests") || v.equals("-Dmaven.test.skip=true"))) throw new SecurityException("test bypass is forbidden");
    }
}

