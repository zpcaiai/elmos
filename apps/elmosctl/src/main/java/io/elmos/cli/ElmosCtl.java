package io.elmos.cli;

import java.io.PrintStream;
import java.util.Map;
import java.util.Set;

public final class ElmosCtl {
    private static final Set<String> COMMANDS = Set.of("preflight", "install", "status", "backup", "restore",
            "import-bundle", "upgrade", "verify", "diagnostics");
    private static final Set<String> MUTATING = Set.of("install", "restore", "import-bundle", "upgrade");

    private ElmosCtl() {}
    public static void main(String[] args) { System.exit(run(args, System.out, System.err)); }

    public static int run(String[] args, PrintStream out, PrintStream error) {
        if (args.length == 0 || !COMMANDS.contains(args[0])) {
            error.println("{\"status\":\"REJECTED\",\"reasonCode\":\"UNKNOWN_COMMAND\",\"commands\":" + jsonArray(COMMANDS) + "}");
            return 2;
        }
        String command = args[0];
        boolean evidenceFlag = java.util.Arrays.asList(args).contains("--evidence-approved");
        boolean confirmation = java.util.Arrays.asList(args).contains("--confirm");
        if (MUTATING.contains(command) && (!evidenceFlag || !confirmation)) {
            error.println("{\"command\":\"" + command + "\",\"status\":\"BLOCKED\",\"reasonCode\":\"APPROVED_EVIDENCE_AND_CONFIRMATION_REQUIRED\"}");
            return 3;
        }
        Map<String,String> status = switch (command) {
            case "preflight" -> Map.of("status", "NOT_RUN", "reasonCode", "TARGET_INSTALLATION_REQUIRED");
            case "status" -> Map.of("status", "NOT_CONFIGURED", "reasonCode", "INSTALLATION_CONTEXT_REQUIRED");
            case "verify" -> Map.of("status", "NOT_RUN", "reasonCode", "RELEASE_BUNDLE_OR_INSTALLATION_REQUIRED");
            case "diagnostics" -> Map.of("status", "NOT_RUN", "reasonCode", "REDACTED_DIAGNOSTIC_TARGET_REQUIRED");
            case "backup" -> Map.of("status", "BLOCKED", "reasonCode", "BACKUP_TARGET_AND_KEY_REQUIRED");
            default -> Map.of("status", "ACCEPTED_FOR_EXTERNAL_EXECUTION", "reasonCode", "RUN_IN_APPROVED_PRIVATE_ENVIRONMENT");
        };
        out.println("{\"command\":\"" + command + "\",\"status\":\"" + status.get("status")
                + "\",\"reasonCode\":\"" + status.get("reasonCode") + "\"}");
        return status.get("status").startsWith("ACCEPTED") ? 0 : 4;
    }

    private static String jsonArray(Set<String> values) {
        return values.stream().sorted().map(value -> "\"" + value + "\"")
                .collect(java.util.stream.Collectors.joining(",", "[", "]"));
    }
}
