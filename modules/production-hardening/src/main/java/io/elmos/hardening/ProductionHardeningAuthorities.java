package io.elmos.hardening;

import java.util.List;
import java.util.Map;

import static io.elmos.hardening.ProductionHardeningModels.*;

/**
 * External evidence authorities used by Batch 10. Implementations may drive isolated load,
 * security, chaos and release labs; the core module never shells out or touches production.
 */
public record ProductionHardeningAuthorities(
        EnvironmentCalibrationAuthority environment,
        PerformanceAuthority performance,
        SecurityAuthority security,
        ReliabilityAuthority reliability,
        ObservabilityAuthority observability,
        ReleaseAuthority release,
        CostAuthority cost) {

    public ProductionHardeningAuthorities {
        ProductionHardeningModels.required(environment, "environment authority");
        ProductionHardeningModels.required(performance, "performance authority");
        ProductionHardeningModels.required(security, "security authority");
        ProductionHardeningModels.required(reliability, "reliability authority");
        ProductionHardeningModels.required(observability, "observability authority");
        ProductionHardeningModels.required(release, "release authority");
        ProductionHardeningModels.required(cost, "cost authority");
    }

    @FunctionalInterface public interface EnvironmentCalibrationAuthority {
        List<ServiceCalibration> calibrate(Request request);
    }

    @FunctionalInterface public interface PerformanceAuthority {
        List<PerformanceEvidence> assess(Request request, Map<String, ServiceCalibration> calibrations);
    }

    @FunctionalInterface public interface SecurityAuthority {
        List<SecurityEvidence> assess(Request request);
    }

    @FunctionalInterface public interface ReliabilityAuthority {
        List<ReliabilityEvidence> assess(Request request);
    }

    @FunctionalInterface public interface ObservabilityAuthority {
        List<ObservabilityEvidence> assess(Request request);
    }

    @FunctionalInterface public interface ReleaseAuthority {
        List<ReleaseEvidence> assess(Request request);
    }

    @FunctionalInterface public interface CostAuthority {
        List<CostEvidence> assess(Request request);
    }
}
