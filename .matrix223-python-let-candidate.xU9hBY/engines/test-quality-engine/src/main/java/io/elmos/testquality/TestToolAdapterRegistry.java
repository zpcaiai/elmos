package io.elmos.testquality;

import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.testquality.QualityModels.*;

public final class TestToolAdapterRegistry {
    private final List<ToolAdapter> adapters = List.of(
            adapter("junit", "JUnit", Set.of(TestType.UNIT, TestType.COMPONENT, TestType.INTEGRATION), Set.of(RunnerType.UNIT, RunnerType.INTEGRATION), "JUnit XML", "EPL-2.0"),
            adapter("dotnet-test", "dotnet test", Set.of(TestType.UNIT, TestType.COMPONENT, TestType.INTEGRATION), Set.of(RunnerType.UNIT, RunnerType.INTEGRATION), "TRX/JUnit XML", "MIT"),
            adapter("pytest", "pytest", Set.of(TestType.UNIT, TestType.COMPONENT, TestType.INTEGRATION), Set.of(RunnerType.UNIT, RunnerType.INTEGRATION), "JUnit XML", "MIT"),
            adapter("javascript-test", "Jest/Vitest", Set.of(TestType.UNIT, TestType.COMPONENT), Set.of(RunnerType.UNIT), "JUnit JSON", "MIT"),
            adapter("playwright", "Playwright", Set.of(TestType.E2E, TestType.VISUAL, TestType.ACCESSIBILITY), Set.of(RunnerType.BROWSER_CLIENT), "Playwright JSON", "Apache-2.0"),
            adapter("pact", "Pact compatible provider", Set.of(TestType.CONTRACT), Set.of(RunnerType.INTEGRATION), "Contract verification", "OPTIONAL_PROVIDER"),
            adapter("hypothesis", "Hypothesis compatible provider", Set.of(TestType.PROPERTY), Set.of(RunnerType.UNIT), "Property result", "OPTIONAL_PROVIDER"),
            adapter("pit", "PIT", Set.of(TestType.MUTATION), Set.of(RunnerType.MUTATION), "Mutation XML", "Apache-2.0"),
            adapter("stryker", "Stryker", Set.of(TestType.MUTATION), Set.of(RunnerType.MUTATION), "Mutation JSON", "Apache-2.0"),
            adapter("testcontainers", "Testcontainers compatible provider", Set.of(TestType.INTEGRATION), Set.of(RunnerType.INTEGRATION), "Environment manifest", "OPTIONAL_PROVIDER"),
            adapter("wiremock", "WireMock compatible provider", Set.of(TestType.CONTRACT, TestType.INTEGRATION), Set.of(RunnerType.INTEGRATION), "Virtual service report", "OPTIONAL_PROVIDER"),
            adapter("test-management", "Test management adapter", Set.of(TestType.E2E), Set.of(RunnerType.BROWSER_CLIENT), "Normalized test inventory", "OPTIONAL_PROVIDER")
    );

    public List<ToolAdapter> adapters() { return adapters; }
    public List<String> statusSummary() { return adapters.stream().map(a -> a.adapterId() + ":" + a.status()).toList(); }
    public Map<AdapterStatus, Long> counts() {
        return adapters.stream().collect(java.util.stream.Collectors.groupingBy(ToolAdapter::status, java.util.stream.Collectors.counting()));
    }

    private static ToolAdapter adapter(String id, String framework, Set<TestType> testTypes,
                                       Set<RunnerType> runners, String report, String license) {
        return new ToolAdapter(id, framework, "PINNED_BY_RUNNER_IMAGE", AdapterStatus.NOT_CONFIGURED,
                testTypes, runners, Set.of("READ_IMMUTABLE_SNAPSHOT", "WRITE_EPHEMERAL_WORKSPACE"),
                true, true, true, report, license, "DENY");
    }
}
