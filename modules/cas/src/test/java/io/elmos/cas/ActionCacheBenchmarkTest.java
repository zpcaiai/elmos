package io.elmos.cas;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Gates ELMOS-CAS-041. Deliberately asserts all four scenarios rather than only the headline hit
 * rate: a cache that ignored the toolchain digest would score a perfect unchanged-rerun rate and
 * be catastrophically wrong.
 */
class ActionCacheBenchmarkTest {

    private static ActionCacheBenchmark.Scenario scenario(ActionCacheBenchmark.Report report, String name) {
        return report.scenarios().stream().filter(entry -> entry.name().equals(name)).findFirst().orElseThrow();
    }

    @Test void unchangedRerunsMeetTheNinetyFivePercentGoal() {
        var report = new ActionCacheBenchmark(120, 12).run();
        assertTrue(report.exactRerunHitRate() >= 0.95,
                "exact rerun hit rate was " + report.exactRerunHitRate());
        assertEquals(1.0d, scenario(report, "unchanged-rerun").hitRate());
        assertEquals(0, scenario(report, "unchanged-rerun").misses());
    }

    @Test void oneChangedFileInvalidatesExactlyOneModule() {
        var report = new ActionCacheBenchmark(120, 12).run();
        var changed = scenario(report, "one-file-changed");
        assertEquals(1, changed.misses(), "over-invalidation: " + changed.missedModules());
        assertEquals(List.of("module-60"), changed.missedModules());
    }

    @Test void aChangedToolchainCannotHitAnyOldOutput() {
        var report = new ActionCacheBenchmark(50, 8).run();
        var toolchain = scenario(report, "toolchain-changed");
        assertEquals(0, toolchain.hits());
        assertEquals(0.0d, toolchain.hitRate());
    }

    @Test void aDowngradedReaderIsDeniedEveryEntry() {
        var report = new ActionCacheBenchmark(50, 8).run();
        assertEquals(0, scenario(report, "permission-downgraded").hits());
        Map<String, Long> reasons = report.outcomeReasons();
        assertEquals(Long.valueOf(50), reasons.get("ACTION/DENIED/PERMISSION_DOWNGRADE"));
    }

    @Test void savingsAreMeasuredFromTheRecordedResultNotGuessed() {
        var report = new ActionCacheBenchmark(10, 4).run();
        // 10 unchanged hits + 9 hits in the changed round, each recording 61 wall seconds.
        assertEquals(19 * 61_000L, report.wallMillisAvoided());
        assertEquals(19 * 42_000L, report.computeMillisAvoided());
        assertEquals(19 * 5_000_000L, report.bytesAvoided());
    }

    @Test void theReportRendersTheGoalAndTheHonestyCaveat() {
        String markdown = new ActionCacheBenchmark(5, 2).run().toMarkdown();
        assertTrue(markdown.contains("goal >= 0.95"));
        assertTrue(markdown.contains("not build times on a real repository"));
    }
}
