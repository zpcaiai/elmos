package io.elmos.worker;

import org.junit.jupiter.api.Test;

import java.nio.file.Path;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class SpringUpgradeConfigurationTest {
    @Test
    void legacyHomesAndAdditionalLegacyJdksFormOneExactRegistry() {
        Map<String, Path> homes = SpringUpgradeConfiguration.javaHomes(
                "/opt/java/openjdk-17",
                "/opt/java/openjdk",
                "8=/opt/java/openjdk-8,11=/opt/java/openjdk-11"
        );

        assertEquals(Map.of(
                "8", Path.of("/opt/java/openjdk-8"),
                "11", Path.of("/opt/java/openjdk-11"),
                "17", Path.of("/opt/java/openjdk-17"),
                "21", Path.of("/opt/java/openjdk")
        ), homes);
    }

    @Test
    void emptyAdditionalRegistryPreservesTheOriginalSeventeenAndTwentyOneContract() {
        Map<String, Path> homes = SpringUpgradeConfiguration.javaHomes(
                "/legacy/java-17", "/legacy/java-21", "");

        assertEquals(Map.of(
                "17", Path.of("/legacy/java-17"),
                "21", Path.of("/legacy/java-21")
        ), homes);
    }

    @Test
    void additionalHomesMustBeExactAbsoluteReleaseMappings() {
        assertThrows(IllegalArgumentException.class, () -> SpringUpgradeConfiguration.javaHomes(
                "/legacy/java-17", "/legacy/java-21", "11=relative/jdk-11"));
        assertThrows(IllegalArgumentException.class, () -> SpringUpgradeConfiguration.javaHomes(
                "/legacy/java-17", "/legacy/java-21", "11"));
    }
}
