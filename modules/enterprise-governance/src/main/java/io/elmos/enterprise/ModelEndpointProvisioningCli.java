package io.elmos.enterprise;

import io.elmos.enterprise.EnterpriseModels.ModelProviderType;
import io.elmos.enterprise.ModelEndpointProvisioning.ProvisioningResult;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;

/**
 * Runs real provisioning attempts (real code path, no fakes) for every model
 * in {@link ModelCatalog#MODEL_IDS} using the default, unwired collaborators:
 * {@link EnvModelCredentialSource} (no env vars set today) and
 * {@link UnimplementedModelHealthProbe} (no vendor client exists yet).
 *
 * Every model is therefore expected to come back {@code approved=false} with
 * reason {@code CREDENTIAL_NOT_CONFIGURED} until an operator wires a real
 * credential and a real {@link ModelHealthProbe} implementation for that
 * vendor — this CLI does not simulate success either way. It writes the
 * per-model evidence as JSON to the given path (or prints to stdout with no
 * argument) so the current state is inspectable without reading Java source.
 */
public final class ModelEndpointProvisioningCli {
    private ModelEndpointProvisioningCli() {}

    public static void main(String[] args) throws IOException {
        String json = run(new EnvModelCredentialSource(), new UnimplementedModelHealthProbe());
        if (args.length == 0) {
            System.out.println(json);
            return;
        }
        Path output = Path.of(args[0]);
        if (output.getParent() != null) {
            Files.createDirectories(output.getParent());
        }
        Files.writeString(output, json, StandardCharsets.UTF_8);
        System.out.println("wrote " + output);
    }

    static String run(ModelCredentialSource credentialSource, ModelHealthProbe healthProbe) {
        var provisioning = new ModelEndpointProvisioning(credentialSource, healthProbe);
        List<ProvisioningResult> results = ModelCatalog.MODEL_IDS.stream()
                .map(modelId -> provisioning.provision("org-unassigned", "catalog:" + modelId,
                        ModelProviderType.ELMOS_MANAGED, "unassigned", modelId, Set.of("CODING_AGENT")))
                .toList();
        return toJson(results);
    }

    private static String toJson(List<ProvisioningResult> results) {
        StringBuilder json = new StringBuilder();
        json.append("{\n  \"catalogVersion\": \"1.0\",\n  \"results\": [\n");
        for (int i = 0; i < results.size(); i++) {
            ProvisioningResult result = results.get(i);
            json.append("    {\n");
            json.append("      \"modelId\": \"").append(escape(result.modelId())).append("\",\n");
            json.append("      \"approved\": ").append(result.approved()).append(",\n");
            json.append("      \"reasonCodes\": [");
            for (int j = 0; j < result.reasonCodes().size(); j++) {
                if (j > 0) json.append(", ");
                json.append('"').append(escape(result.reasonCodes().get(j))).append('"');
            }
            json.append("]\n    }");
            if (i < results.size() - 1) json.append(',');
            json.append('\n');
        }
        json.append("  ]\n}\n");
        return json.toString();
    }

    private static String escape(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"");
    }
}
