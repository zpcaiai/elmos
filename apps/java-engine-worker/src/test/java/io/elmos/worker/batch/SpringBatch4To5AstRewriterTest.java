package io.elmos.worker.batch;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringBatch4To5AstRewriterTest {
    @TempDir Path root;

    @Test void rewritesFactoriesThroughCompilerAstAndPreservesCommentsAndStrings() throws Exception {
        Path source = root.resolve("BatchConfig.java");
        Files.writeString(source, """
                package com.acme;
                import org.springframework.batch.core.configuration.annotation.JobBuilderFactory;
                import org.springframework.batch.core.configuration.annotation.StepBuilderFactory;
                import org.springframework.transaction.PlatformTransactionManager;
                class BatchConfig {
                    private final JobBuilderFactory jobs;
                    private final StepBuilderFactory steps;
                    private final PlatformTransactionManager transactionManager;
                    // jobs.get("comment") must remain untouched
                    String sample = "steps.get(\\\"string\\\")";
                    Object job(Object step) { return jobs.get("orders").start(step).build(); }
                    Object step() { return steps.get("load").chunk(50).build(); }
                }
                """);
        var result = SpringBatch4To5AstRewriter.modernize(root);
        assertTrue(result.modified());
        assertTrue(result.blockingObligations().isEmpty());
        String rewritten = Files.readString(source);
        assertTrue(rewritten.contains("new JobBuilder(\"orders\", jobs)"));
        assertTrue(rewritten.contains("new StepBuilder(\"load\", steps).chunk(50, transactionManager)"));
        assertTrue(rewritten.contains("// jobs.get(\"comment\") must remain untouched"));
        assertTrue(rewritten.contains("\"steps.get(\\\"string\\\")\""));
        assertFalse(rewritten.contains("import org.springframework.batch.core.configuration.annotation.JobBuilderFactory"));
    }

    @Test void blocksChunkRewriteWithoutTransactionManager() throws Exception {
        Path source = root.resolve("BatchConfig.java");
        String before = "class BatchConfig { StepBuilderFactory steps; Object step(){ return steps.get(\"x\").chunk(1).build(); } }";
        Files.writeString(source, before);
        var result = SpringBatch4To5AstRewriter.modernize(root);
        assertFalse(result.modified());
        assertFalse(result.blockingObligations().isEmpty());
        assertTrue(Files.readString(source).equals(before));
    }
}
