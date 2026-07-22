package io.elmos.recipes;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class RewriteSpringFoundationTest {
    @Test void lockedDependencyPublishesSpringBootRecipeCatalog() {
        assertNotNull(getClass().getClassLoader().getResource("META-INF/rewrite/spring-boot-35.yml"));
        assertEquals("org.openrewrite.recipe:rewrite-spring:6.35.0", RewriteSpringFoundation.COORDINATE);
    }
}

