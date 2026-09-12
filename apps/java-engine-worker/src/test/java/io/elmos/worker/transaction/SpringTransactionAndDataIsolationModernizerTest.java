package io.elmos.worker.transaction;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringTransactionAndDataIsolationModernizerTest {

    @Test
    @DisplayName("Modernize bare @Transactional with explicit rollbackFor = Exception.class")
    void testBareTransactionalRollbackFor() {
        String source = "package com.example;\n"
                + "import org.springframework.transaction.annotation.Transactional;\n"
                + "public class AccountService {\n"
                + "    @Transactional\n"
                + "    public void transferMoney(Long from, Long to, Double amount) {\n"
                + "        // transfer logic\n"
                + "    }\n"
                + "}";

        var result = SpringTransactionAndDataIsolationModernizer.modernizeContent(source, "AccountService.java");

        assertTrue(result.modified());
        String modernized = result.rulesApplied().get(0);
        assertTrue(modernized.contains("@Transactional(rollbackFor = Exception.class)"));
    }

    @Test
    @DisplayName("Modernize HibernateTransactionManager to JpaTransactionManager")
    void testHibernateTxManagerMigration() {
        String source = "package com.example.config;\n"
                + "import org.springframework.orm.hibernate5.HibernateTransactionManager;\n"
                + "import org.springframework.context.annotation.Bean;\n"
                + "public class TxConfig {\n"
                + "    @Bean\n"
                + "    public HibernateTransactionManager transactionManager() {\n"
                + "        return new HibernateTransactionManager();\n"
                + "    }\n"
                + "}";

        var result = SpringTransactionAndDataIsolationModernizer.modernizeContent(source, "TxConfig.java");

        assertTrue(result.modified());
        String modernized = result.rulesApplied().get(0);
        assertFalse(modernized.contains("org.springframework.orm.hibernate5.HibernateTransactionManager"));
        assertTrue(modernized.contains("org.springframework.orm.jpa.JpaTransactionManager"));
        assertTrue(modernized.contains("return new JpaTransactionManager();"));
    }

    @Test
    @DisplayName("Audit non-public @Transactional and swallowed exception risks")
    void testTransactionAuditRisks() {
        String source = "package com.example;\n"
                + "import org.springframework.transaction.annotation.Transactional;\n"
                + "public class RiskyService {\n"
                + "    @Transactional\n"
                + "    private void internalUpdate() {\n"
                + "        try {\n"
                + "            // db write\n"
                + "        } catch (Exception e) // ignore\n"
                + "        {}\n"
                + "    }\n"
                + "}";

        var result = SpringTransactionAndDataIsolationModernizer.modernizeContent(source, "RiskyService.java");

        assertNotNull(result.auditFindings());
        assertFalse(result.auditFindings().isEmpty());
        assertTrue(result.auditFindings().stream()
                .anyMatch(f -> f.risk() == SpringTransactionAndDataIsolationModernizer.TransactionRisk.NON_PUBLIC_TRANSACTIONAL_METHOD));
        assertTrue(result.auditFindings().stream()
                .anyMatch(f -> f.risk() == SpringTransactionAndDataIsolationModernizer.TransactionRisk.SWALLOWED_EXCEPTION_PREVENTS_ROLLBACK));
    }

    @Test
    @DisplayName("Modernize transaction workspace directory on disk")
    void testWorkspaceTransactionModernization(@TempDir Path tempDir) throws IOException {
        Path javaDir = tempDir.resolve("src/main/java/com/example");
        Files.createDirectories(javaDir);
        Files.writeString(javaDir.resolve("TxBean.java"),
                "package com.example;\nimport org.springframework.transaction.annotation.Transactional;\npublic class TxBean { @Transactional public void execute() {} }");

        var result = SpringTransactionAndDataIsolationModernizer.modernize(tempDir);

        assertTrue(result.modified());
        String updated = Files.readString(javaDir.resolve("TxBean.java"));
        assertTrue(updated.contains("@Transactional(rollbackFor = Exception.class)"));
    }
}
