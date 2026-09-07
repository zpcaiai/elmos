package io.elmos.recipes;

import java.util.List;

public final class RewriteSpringFoundation {
    public static final String COORDINATE = "org.openrewrite.recipe:rewrite-spring:6.35.0";
    public static final List<String> MVP_RECIPES = List.of(
            "org.openrewrite.java.migrate.UpgradeToJava21",
            "org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_5");
    private RewriteSpringFoundation() {}
}

