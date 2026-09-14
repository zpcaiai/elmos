package io.elmos.worker;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Pattern;

/** Evidence gate for promoting exact Spring routes without editing catalog claims by hand. */
public final class SpringRouteQualificationGate {
    private static final Pattern SHA_256 = Pattern.compile("sha256:[0-9a-f]{64}");
    private static final Pattern COMMIT = Pattern.compile("[0-9a-f]{40}");

    public enum LocalStatus { PASSED_LOCAL, NOT_RUN }
    public enum ExternalStatus { READY_FOR_EXTERNAL_GATE, NOT_RUN }

    public record RouteExecutionEvidence(
            String routeId,
            String sourceVersion,
            String sourceJava,
            String sourceCommit,
            String targetCommit,
            String artifactDigest,
            boolean sourceBuildPassed,
            boolean sourceStartupPassed,
            boolean targetBuildPassed,
            boolean targetStartupPassed,
            boolean p0ContractsPassed,
            boolean holdoutPassed,
            boolean representativeRepositoryPassed,
            boolean customerRepositoryAuthorized,
            boolean customerAcceptancePassed,
            boolean independentVerificationPassed
    ) {}

    public record RouteDecision(
            String routeId,
            LocalStatus localStatus,
            ExternalStatus externalStatus,
            List<String> blockers
    ) {}

    public record MatrixDecision(
            int catalogRoutes,
            int alreadyPassedLocal,
            int pendingRoutes,
            int newlyQualifiedLocal,
            int readyForExternalGate,
            Map<String, RouteDecision> decisions
    ) {}

    private SpringRouteQualificationGate() {}

    public static List<String> pendingRouteIds() {
        return SpringRouteCatalog.routes().stream()
                .filter(route -> route.routeEvidence() == SpringRouteCatalog.EvidenceStatus.NOT_RUN)
                .map(SpringRouteCatalog.SpringRoute::routeId)
                .toList();
    }

    public static RouteDecision evaluate(RouteExecutionEvidence evidence) {
        Objects.requireNonNull(evidence, "evidence must not be null");
        SpringRouteCatalog.SpringRoute route = SpringRouteCatalog.byId(evidence.routeId())
                .orElse(null);
        List<String> blockers = new ArrayList<>();
        if (route == null) {
            return new RouteDecision(evidence.routeId(), LocalStatus.NOT_RUN, ExternalStatus.NOT_RUN,
                    List.of("route is not declared in SpringRouteCatalog"));
        }
        if (!route.acceptsSourceVersion(evidence.sourceVersion()))
            blockers.add("source version is outside the exact directed route");
        if (!route.sourceJavaVersions().contains(SpringRouteCatalog.normalizeJava(evidence.sourceJava())))
            blockers.add("source Java is outside the declared route tuple");
        if (!COMMIT.matcher(nullToEmpty(evidence.sourceCommit())).matches())
            blockers.add("source commit must be a full immutable Git SHA");
        if (!COMMIT.matcher(nullToEmpty(evidence.targetCommit())).matches())
            blockers.add("target commit must be a full immutable Git SHA");
        if (!SHA_256.matcher(nullToEmpty(evidence.artifactDigest())).matches())
            blockers.add("target artifact must have a lowercase sha256 digest");
        require(evidence.sourceBuildPassed(), "source build did not pass", blockers);
        require(evidence.sourceStartupPassed(), "source startup did not pass", blockers);
        require(evidence.targetBuildPassed(), "target build did not pass", blockers);
        require(evidence.targetStartupPassed(), "target startup did not pass", blockers);
        require(evidence.p0ContractsPassed(), "P0 framework contracts did not pass", blockers);
        require(evidence.holdoutPassed(), "independent holdout did not pass", blockers);
        require(evidence.representativeRepositoryPassed(), "representative repository did not pass", blockers);

        LocalStatus local = blockers.isEmpty() ? LocalStatus.PASSED_LOCAL : LocalStatus.NOT_RUN;
        List<String> externalBlockers = new ArrayList<>(blockers);
        require(evidence.customerRepositoryAuthorized(), "customer repository authorization is absent", externalBlockers);
        require(evidence.customerAcceptancePassed(), "customer acceptance did not pass", externalBlockers);
        require(evidence.independentVerificationPassed(), "independent verification did not pass", externalBlockers);
        ExternalStatus external = externalBlockers.isEmpty()
                ? ExternalStatus.READY_FOR_EXTERNAL_GATE : ExternalStatus.NOT_RUN;
        return new RouteDecision(route.routeId(), local, external, List.copyOf(externalBlockers));
    }

    public static MatrixDecision evaluateMatrix(List<RouteExecutionEvidence> evidence) {
        Objects.requireNonNull(evidence, "evidence must not be null");
        Map<String, RouteExecutionEvidence> byRoute = new LinkedHashMap<>();
        for (RouteExecutionEvidence item : evidence) {
            if (byRoute.putIfAbsent(item.routeId(), item) != null)
                throw new IllegalArgumentException("duplicate route evidence: " + item.routeId());
        }
        Map<String, RouteDecision> decisions = new LinkedHashMap<>();
        int newlyQualified = 0;
        int externalReady = 0;
        Set<String> pending = Set.copyOf(pendingRouteIds());
        for (String routeId : pendingRouteIds()) {
            RouteExecutionEvidence item = byRoute.get(routeId);
            RouteDecision decision = item == null
                    ? new RouteDecision(routeId, LocalStatus.NOT_RUN, ExternalStatus.NOT_RUN,
                    List.of("no exact execution evidence supplied"))
                    : evaluate(item);
            decisions.put(routeId, decision);
            if (decision.localStatus() == LocalStatus.PASSED_LOCAL) newlyQualified++;
            if (decision.externalStatus() == ExternalStatus.READY_FOR_EXTERNAL_GATE) externalReady++;
        }
        for (String supplied : byRoute.keySet()) {
            if (!pending.contains(supplied) && SpringRouteCatalog.byId(supplied).isEmpty())
                decisions.put(supplied, evaluate(byRoute.get(supplied)));
        }
        int already = SpringRouteCatalog.verifiedRoutes().size();
        return new MatrixDecision(SpringRouteCatalog.routes().size(), already, pending.size(),
                newlyQualified, externalReady, Map.copyOf(decisions));
    }

    private static void require(boolean condition, String blocker, List<String> blockers) {
        if (!condition) blockers.add(blocker);
    }

    private static String nullToEmpty(String value) {
        return value == null ? "" : value;
    }
}
