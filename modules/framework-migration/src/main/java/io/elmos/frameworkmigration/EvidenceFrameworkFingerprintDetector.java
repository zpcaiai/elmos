package io.elmos.frameworkmigration;

import io.elmos.skeleton.SkeletonModels;

import java.util.*;
import java.util.stream.Collectors;

import static io.elmos.frameworkmigration.FrameworkMigrationModels.*;

/** Evidence-only detector for the five Batch 7 framework families. It never loads application code. */
public final class EvidenceFrameworkFingerprintDetector implements FingerprintDetector {
    @Override
    public FrameworkFingerprint detect(List<FrameworkSignal> supplied,
                                       SkeletonModels.TargetProfile targetProfile) {
        List<FrameworkSignal> signals = supplied == null ? List.of() : supplied.stream()
                .filter(Objects::nonNull)
                .filter(signal -> signal.kind() != null && signal.value() != null
                        && signal.sourceRef() != null && !signal.sourceRef().isBlank())
                .toList();
        Map<String,List<FrameworkSignal>> matches = new LinkedHashMap<>();
        for (String family : List.of("spring-boot", "fastapi", "aspnet-core", "nestjs", "express")) {
            matches.put(family, new ArrayList<>());
        }
        for (FrameworkSignal signal : signals) {
            String value = signal.value().toLowerCase(Locale.ROOT);
            if (containsAny(value, "spring-boot", "@restcontroller", "@controller", "webflux", "spring.mvc"))
                matches.get("spring-boot").add(signal);
            if (containsAny(value, "fastapi", "apirouter", "depends(", "pydantic"))
                matches.get("fastapi").add(signal);
            if (containsAny(value, "microsoft.aspnetcore", "mapget(", "mapcontrollers", "controllerbase"))
                matches.get("aspnet-core").add(signal);
            if (containsAny(value, "@nestjs/", "@controller(", "@module(", "nestfactory"))
                matches.get("nestjs").add(signal);
            if (containsAny(value, "express", "express.router", "router.get(", "router.post("))
                matches.get("express").add(signal);
        }
        if (!matches.get("nestjs").isEmpty()) {
            matches.get("express").removeIf(signal -> signal.value().toLowerCase(Locale.ROOT).contains("express"));
        }
        List<Map.Entry<String,List<FrameworkSignal>>> ranked = matches.entrySet().stream()
                .filter(entry -> !entry.getValue().isEmpty())
                .sorted(Comparator.<Map.Entry<String,List<FrameworkSignal>>>comparingInt(entry -> distinctKinds(entry.getValue())).reversed()
                        .thenComparing(entry -> entry.getValue().size(), Comparator.reverseOrder())
                        .thenComparing(Map.Entry::getKey))
                .toList();
        List<String> diagnostics = new ArrayList<>();
        if (ranked.isEmpty()) {
            diagnostics.add("framework-family-not-detected");
            return fingerprint("unknown", "unknown", "unknown", null, null, 0, false, List.of(), List.of(), diagnostics);
        }
        Map.Entry<String,List<FrameworkSignal>> selected = ranked.getFirst();
        if (ranked.size() > 1 && distinctKinds(ranked.get(1).getValue()) == distinctKinds(selected.getValue())
                && ranked.get(1).getValue().size() == selected.getValue().size()) {
            diagnostics.add("ambiguous-framework-families:" + selected.getKey() + "," + ranked.get(1).getKey());
        }
        String family = selected.getKey();
        List<FrameworkSignal> evidence = selected.getValue().stream()
                .sorted(Comparator.comparing(FrameworkSignal::sourceRef).thenComparing(FrameworkSignal::value)).toList();
        String values = evidence.stream().map(FrameworkSignal::value).collect(Collectors.joining(" ")).toLowerCase(Locale.ROOT);
        String webMode = switch (family) {
            case "spring-boot" -> values.contains("webflux") || values.contains("reactive") ? "reactive" : "servlet";
            case "aspnet-core" -> values.contains("mapget(") || values.contains("minimal") ? "minimal-api" : "controller";
            default -> "async-request-response";
        };
        if (family.equals("spring-boot") && values.contains("webflux")
                && (values.contains("spring-mvc") || values.contains("starter-web"))) {
            diagnostics.add("mixed-spring-mvc-and-webflux");
        }
        String programmingModel = switch (family) {
            case "spring-boot" -> "annotated-controller";
            case "fastapi" -> "decorated-path-operation";
            case "aspnet-core" -> webMode.equals("minimal-api") ? "minimal-api" : "controller";
            case "nestjs" -> "decorated-controller";
            default -> "router-middleware";
        };
        String adapter = family.equals("nestjs")
                ? (values.contains("fastify") ? "fastify" : values.contains("express") ? "express" : null) : null;
        String version = signals.stream().filter(signal -> signal.kind().equalsIgnoreCase("framework-version"))
                .map(FrameworkSignal::value).filter(value -> !value.isBlank()).findFirst().orElse(null);
        if (version == null) diagnostics.add("framework-version-unresolved");
        int evidenceKinds = distinctKinds(evidence);
        if (evidenceKinds < 2) diagnostics.add("framework-fingerprint-needs-two-independent-evidence-kinds");
        boolean complete = diagnostics.isEmpty();
        double confidence = Math.min(1.0, 0.35 + evidenceKinds * 0.25 + Math.min(0.15, evidence.size() * 0.03));
        List<String> components = evidence.stream().map(FrameworkSignal::value).distinct().sorted().toList();
        return fingerprint(family, webMode, programmingModel, adapter, version, confidence,
                complete, evidence, components, diagnostics);
    }

    private FrameworkFingerprint fingerprint(String family, String webMode, String programmingModel,
                                             String adapter, String version, double confidence,
                                             boolean complete, List<FrameworkSignal> evidence,
                                             List<String> components, List<String> diagnostics) {
        String id = FrameworkIds.id("framework-instance", family, webMode, programmingModel, adapter,
                version, evidence);
        return new FrameworkFingerprint(id, family, webMode, programmingModel, adapter, version,
                confidence, complete, evidence, components, diagnostics);
    }

    private static boolean containsAny(String value, String... needles) {
        return Arrays.stream(needles).anyMatch(value::contains);
    }

    private static int distinctKinds(List<FrameworkSignal> signals) {
        return (int) signals.stream().map(signal -> signal.kind().toLowerCase(Locale.ROOT)).distinct().count();
    }
}
