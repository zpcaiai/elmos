package io.elmos.worker.corpus;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringThirtyProjectsGreenBuildTest {

    @TempDir
    Path temporaryDirectory;

    @Test
    @DisplayName("Verify 100% Green Build Across 30 Real Open Source Complex Projects")
    void testAllThirtyProjectsBuildGreen() throws Exception {
        List<SpringThirtyOpenSourceProjectsCorpus.ProjectSpec> corpus =
                SpringThirtyOpenSourceProjectsCorpus.getCorpus();

        assertEquals(30, corpus.size(), "Corpus must contain exactly 30 representative projects");

        List<SpringThirtyOpenSourceProjectsCorpus.ProjectBuildResult> results = new ArrayList<>();
        int passedCount = 0;

        System.out.println("================================================================================");
        System.out.println("  EXECUTING SPRING 30 OPEN-SOURCE REAL PROJECTS 100% GREEN BUILD BENCHMARK");
        System.out.println("================================================================================");

        for (SpringThirtyOpenSourceProjectsCorpus.ProjectSpec spec : corpus) {
            SpringThirtyOpenSourceProjectsCorpus.ProjectBuildResult res =
                    SpringThirtyOpenSourceProjectsCorpus.executePipeline(spec, temporaryDirectory);

            results.add(res);
            if (res.isGreen()) {
                passedCount++;
            }

            System.out.printf("[%s] Project %s: %s (Rules: %d, Target LOC: %d)\n",
                    res.isGreen() ? "GREEN" : "FAIL",
                    res.projectId(),
                    res.projectName(),
                    res.appliedRulesCount(),
                    res.targetLoc()
            );
        }

        System.out.println("--------------------------------------------------------------------------------");
        System.out.printf("SUMMARY: %d / 30 Projects Passed (%.1f%% Green Rate)\n",
                passedCount, (passedCount * 100.0 / 30.0));
        System.out.println("================================================================================");

        // Assert 100% Green
        assertEquals(30, passedCount, "All 30 projects must pass with 100% green build status");
        for (SpringThirtyOpenSourceProjectsCorpus.ProjectBuildResult r : results) {
            assertTrue(r.isGreen(), "Project " + r.projectId() + " failed: " + r.logs());
        }
    }
}
