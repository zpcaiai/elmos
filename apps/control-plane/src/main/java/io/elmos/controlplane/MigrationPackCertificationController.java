package io.elmos.controlplane;

import io.elmos.migrationpack.MigrationPackAdmissionService;
import io.elmos.migrationpack.MigrationPackCatalog;
import io.elmos.migrationpack.MigrationPackModels.*;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/migration-pack-certification")
public final class MigrationPackCertificationController {
    private final MigrationPackAdmissionService admission = new MigrationPackAdmissionService();

    @GetMapping("/capabilities")
    public List<PackDefinition> capabilities() { return MigrationPackCatalog.all(); }

    @PostMapping("/M{pack}/admission/evaluate")
    public AdmissionResult evaluate(@PathVariable int pack, @RequestBody AdmissionRequest request) {
        if (pack != request.pack()) throw new IllegalArgumentException("path and request migration pack must match");
        return admission.evaluate(request);
    }

    @ExceptionHandler(IllegalArgumentException.class) @ResponseStatus(HttpStatus.BAD_REQUEST)
    Map<String, Object> badRequest(IllegalArgumentException error) {
        return Map.of("errorCode", "MIGRATION_PACK_ADMISSION_REJECTED", "message", error.getMessage(), "retryable", false);
    }
}
