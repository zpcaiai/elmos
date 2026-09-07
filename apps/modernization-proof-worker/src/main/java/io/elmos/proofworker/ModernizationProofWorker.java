package io.elmos.proofworker;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import io.elmos.proofloop.ModernizationProofLoopEngine;
import io.elmos.proofloop.ProofLoopModels;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Map;

/** Container entry point used by Runner Agent; it never shells out or performs provider mutations. */
public final class ModernizationProofWorker {
    private ModernizationProofWorker() {}

    public record WorkerRequest(
            int schemaVersion,
            String targetSkillId,
            ProofLoopModels.ExecutionRequest execution
    ) {
        public WorkerRequest {
            if (schemaVersion != 1) throw new IllegalArgumentException("unsupported worker request schema");
            ProofLoopModels.required(targetSkillId, "targetSkillId");
            ProofLoopModels.required(execution, "execution");
            if (!targetSkillId.equals(execution.skillId())) throw new IllegalArgumentException("target Skill mismatch");
        }
    }

    public static void main(String[] args) throws Exception {
        Path inputDirectory = confinedDirectory(System.getenv().getOrDefault("ELMOS_INPUT_DIR", "/elmos/in"));
        Path outputDirectory = confinedDirectory(System.getenv().getOrDefault("ELMOS_OUTPUT_DIR", "/elmos/out"));
        Files.createDirectories(outputDirectory);
        Path evidenceDirectory = outputDirectory.resolve("evidence");
        Files.createDirectories(evidenceDirectory);

        ObjectMapper mapper = new ObjectMapper().findAndRegisterModules()
                .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
        WorkerRequest request = mapper.readValue(inputDirectory.resolve("request.json").toFile(), WorkerRequest.class);
        ModernizationProofLoopEngine engine = new ModernizationProofLoopEngine();
        ProofLoopModels.PlanResult result = engine.execute(request.targetSkillId(), request.execution());

        Path temporary = Files.createTempFile(evidenceDirectory, "proof-loop-result-", ".tmp");
        mapper.writerWithDefaultPrettyPrinter().writeValue(temporary.toFile(), Map.of(
                "schemaVersion", 1,
                "result", result,
                "externalOperationExecuted", false,
                "productionApproved", false,
                "certified", false));
        Files.move(temporary, evidenceDirectory.resolve("proof-loop-result.json"),
                StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
    }

    private static Path confinedDirectory(String raw) {
        Path path = Path.of(raw).toAbsolutePath().normalize();
        if (!path.isAbsolute()) throw new IllegalArgumentException("worker directory must be absolute");
        return path;
    }
}
