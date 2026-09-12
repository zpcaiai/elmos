package io.elmos.worker;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class SpringHandoffLedgerTest {

    private final ObjectMapper json = new ObjectMapper().findAndRegisterModules();

    @TempDir
    Path tempDir;

    @Test
    void buildManifestWithNoErrorsProducesCleanManifest() {
        var manifest = SpringHandoffLedger.buildManifest(tempDir, List.of(), 5);
        assertEquals("1.0", manifest.schemaVersion());
        assertEquals(0, manifest.handoffItemsCount());
        assertEquals(5, manifest.autoRepairedCount());
        assertEquals(100.0, manifest.dispositionCoveragePercent());
        assertTrue(manifest.handoffItems().isEmpty());
    }

    @Test
    void buildManifestCategorizesDiagnosticsCorrectly() throws Exception {
        List<String> diagnostics = List.of(
                "[ERROR] /app/src/main/java/NativeLib.java:[12,5] native method declaration JNI GetStringUTFChars not supported",
                "[ERROR] /app/src/main/java/PluginLoader.java:[45,10] ClassLoader.defineClass is deprecated and restricted",
                "[ERROR] Could not resolve dependencies for project com.corp:custom-starter:jar:1.0: Failure to find com.oracle:ojdbc6:jar:11.2.0.4",
                "[ERROR] /app/src/main/java/Agent.java:[20,8] cglib Enhancer bytecode transformation failed",
                "[ERROR] /app/src/main/java/Main.java:[88,14] incompatible types: String cannot be converted to int"
        );

        var manifest = SpringHandoffLedger.buildManifest(tempDir, diagnostics, 2);
        assertEquals(5, manifest.handoffItemsCount());
        assertEquals(2, manifest.autoRepairedCount());
        assertEquals(7, manifest.totalIssuesAnalyzed());
        assertEquals(100.0, manifest.dispositionCoveragePercent());

        var items = manifest.handoffItems();
        assertEquals(SpringHandoffLedger.HandoffCategory.JNI_OR_NATIVE_CODE, items.get(0).category());
        assertEquals(SpringHandoffLedger.HandoffCategory.DEPRECATED_CUSTOM_CLASSLOADER, items.get(1).category());
        assertEquals(SpringHandoffLedger.HandoffCategory.PROPRIETARY_DEPENDENCY, items.get(2).category());
        assertEquals(SpringHandoffLedger.HandoffCategory.UNSUPPORTED_BYTECODE_MANIPULATION, items.get(3).category());
        assertEquals(SpringHandoffLedger.HandoffCategory.COMPILATION_ERROR, items.get(4).category());

        for (var item : items) {
            assertEquals("MANUAL_REVIEW_REQUIRED", item.disposition());
            assertNotNull(item.recommendedAction());
            assertFalse(item.recommendedAction().isBlank());
        }

        // Test Jackson round-trip serialization
        String serialized = json.writeValueAsString(manifest);
        var deserialized = json.readValue(serialized, SpringHandoffLedger.HandoffManifest.class);
        assertEquals(manifest.schemaVersion(), deserialized.schemaVersion());
        assertEquals(manifest.handoffItemsCount(), deserialized.handoffItemsCount());
        assertEquals(manifest.dispositionCoveragePercent(), deserialized.dispositionCoveragePercent());
    }
}
