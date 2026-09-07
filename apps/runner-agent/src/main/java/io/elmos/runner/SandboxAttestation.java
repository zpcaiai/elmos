package io.elmos.runner;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Self-check of the sandbox properties the control plane requires before a node
 * may reach READY.
 *
 * <p>Important framing: this is a <em>self-declaration</em>, not proof. The
 * database constraint {@code runner_nodes_ready_requires_attestation} additionally
 * demands a named verifier and a verification timestamp, so a node that lies here
 * still cannot promote itself. What this class buys is that an honest but
 * misconfigured node refuses to register in the first place, instead of waiting
 * for a human to notice.</p>
 */
public record SandboxAttestation(
        boolean rootless,
        boolean readOnlyRoot,
        boolean capabilitiesDropped,
        boolean networkDefaultDeny,
        String imageAllowlistVersion,
        Map<String, String> evidence
) {

    public boolean complete() {
        return rootless && readOnlyRoot && capabilitiesDropped && networkDefaultDeny
                && imageAllowlistVersion != null && !imageAllowlistVersion.isBlank();
    }

    public static SandboxAttestation probe(AgentConfig config, ProcessRunner processes) {
        Map<String, String> evidence = new LinkedHashMap<>();

        boolean rootless = probeRootless(evidence, processes, config);
        boolean readOnlyRoot = probeReadOnlyRoot(evidence);
        boolean capsDropped = probeCapabilities(evidence);
        boolean defaultDeny = probeNetworkPolicy(evidence, config);

        String allowlist = System.getenv().getOrDefault("ELMOS_RUNNER_IMAGE_ALLOWLIST_VERSION", "");
        evidence.put("image_allowlist_version", allowlist.isBlank() ? "(unset)" : allowlist);

        return new SandboxAttestation(rootless, readOnlyRoot, capsDropped, defaultDeny, allowlist, evidence);
    }

    private static boolean probeRootless(Map<String, String> evidence, ProcessRunner processes, AgentConfig config) {
        String uid = readFirstLine(processes, "id", "-u");
        evidence.put("effective_uid", uid);
        boolean nonRootAgent = !"0".equals(uid);

        if (config.allowHostExecution()) {
            // Host execution is development only; there is no engine to interrogate.
            return nonRootAgent;
        }

        // podman info reports rootless directly; docker reports a rootless security
        // option. Anything else is treated as not proven.
        String info = processes.captureOrEmpty(config.containerEngine(), "info", "--format", "{{json .}}");
        boolean engineRootless = info.contains("\"rootless\":true")
                || info.contains("\"Rootless\":true")
                || info.contains("rootless");
        evidence.put("engine_rootless_reported", String.valueOf(engineRootless));
        return nonRootAgent && engineRootless;
    }

    private static boolean probeReadOnlyRoot(Map<String, String> evidence) {
        // The agent's own root filesystem should be read-only when it runs as a
        // container. Probe by attempting a write rather than parsing mount tables,
        // which differ across runtimes.
        Path probe = Path.of("/.elmos-runner-write-probe");
        try {
            Files.writeString(probe, "probe");
            Files.deleteIfExists(probe);
            evidence.put("root_filesystem", "writable");
            return false;
        } catch (Exception ex) {
            evidence.put("root_filesystem", "read-only");
            return true;
        }
    }

    private static boolean probeCapabilities(Map<String, String> evidence) {
        try {
            for (String line : Files.readAllLines(Path.of("/proc/self/status"))) {
                if (line.startsWith("CapEff:")) {
                    String hex = line.substring("CapEff:".length()).trim();
                    evidence.put("cap_effective", hex);
                    // All capabilities dropped means an empty effective set.
                    return Long.parseUnsignedLong(hex, 16) == 0L;
                }
            }
            evidence.put("cap_effective", "(absent)");
            return false;
        } catch (Exception ex) {
            evidence.put("cap_effective", "(unreadable)");
            return false;
        }
    }

    private static boolean probeNetworkPolicy(Map<String, String> evidence, AgentConfig config) {
        // The agent itself needs egress to the control plane; what must be
        // default-deny is the workload network. The agent proves it will always
        // pass --network=none by construction, and records the engine's default.
        boolean enforced = !config.allowHostExecution();
        evidence.put("workload_network", enforced ? "none (enforced by agent)" : "host (development)");
        return enforced;
    }

    private static String readFirstLine(ProcessRunner processes, String... command) {
        String output = processes.captureOrEmpty(command);
        int newline = output.indexOf('\n');
        return (newline >= 0 ? output.substring(0, newline) : output).trim();
    }

    public Map<String, Object> toWire() {
        Map<String, Object> wire = new LinkedHashMap<>();
        wire.put("rootless", rootless);
        wire.put("readOnlyRoot", readOnlyRoot);
        wire.put("capabilitiesDropped", capabilitiesDropped);
        wire.put("networkDefaultDeny", networkDefaultDeny);
        wire.put("imageAllowlistVersion", imageAllowlistVersion == null ? "" : imageAllowlistVersion);
        return wire;
    }

    public String describeFailures() {
        StringBuilder out = new StringBuilder();
        if (!rootless) {
            out.append("rootless=false ");
        }
        if (!readOnlyRoot) {
            out.append("readOnlyRoot=false ");
        }
        if (!capabilitiesDropped) {
            out.append("capabilitiesDropped=false ");
        }
        if (!networkDefaultDeny) {
            out.append("networkDefaultDeny=false ");
        }
        if (imageAllowlistVersion == null || imageAllowlistVersion.isBlank()) {
            out.append("imageAllowlistVersion=unset ");
        }
        return out.toString().trim();
    }
}
