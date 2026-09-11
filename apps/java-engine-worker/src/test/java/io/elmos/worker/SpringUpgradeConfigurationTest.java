package io.elmos.worker;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.nio.file.Path;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class SpringUpgradeConfigurationTest {
    @Test
    void legacyHomesAndAdditionalLegacyJdksFormOneExactRegistry() {
        Path base = Path.of(System.getProperty("java.io.tmpdir")).toAbsolutePath().normalize();
        Path java8 = base.resolve("java-8");
        Path java11 = base.resolve("java-11");
        Path java17 = base.resolve("java-17");
        Path java21 = base.resolve("java-21");
        Map<String, Path> homes = SpringUpgradeConfiguration.javaHomes(
                java17.toString(),
                java21.toString(),
                "8=" + java8 + ",11=" + java11
        );

        assertEquals(Map.of(
                "8", java8,
                "11", java11,
                "17", java17,
                "21", java21
        ), homes);
    }

    @Test
    void emptyAdditionalRegistryPreservesTheOriginalSeventeenAndTwentyOneContract() {
        Path base = Path.of(System.getProperty("java.io.tmpdir")).toAbsolutePath().normalize();
        Path java17 = base.resolve("legacy-java-17");
        Path java21 = base.resolve("legacy-java-21");
        Map<String, Path> homes = SpringUpgradeConfiguration.javaHomes(
                java17.toString(), java21.toString(), "");

        assertEquals(Map.of(
                "17", java17,
                "21", java21
        ), homes);
    }

    @Test
    void additionalHomesMustBeExactAbsoluteReleaseMappings() {
        Path base = Path.of(System.getProperty("java.io.tmpdir")).toAbsolutePath().normalize();
        String java17 = base.resolve("legacy-java-17").toString();
        String java21 = base.resolve("legacy-java-21").toString();
        assertThrows(IllegalArgumentException.class, () -> SpringUpgradeConfiguration.javaHomes(
                java17, java21, "11=relative/jdk-11"));
        assertThrows(IllegalArgumentException.class, () -> SpringUpgradeConfiguration.javaHomes(
                java17, java21, "11"));
    }

    @Test
    void consumedTomcatManifestDigestIsPassedIntoRuntimeConfiguration() {
        String digest = "a".repeat(64);
        SpringMvcWarRuntime.Configuration configuration =
                SpringUpgradeConfiguration.springMvcRuntimeConfiguration(
                        "", "9.0.83", "b".repeat(64), digest, "", "", new ObjectMapper());

        assertEquals(digest, configuration.consumedTomcatManifestSha256());
    }
}
