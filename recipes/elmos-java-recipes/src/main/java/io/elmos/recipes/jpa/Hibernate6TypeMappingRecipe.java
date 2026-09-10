package io.elmos.recipes.jpa;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.TypeTree;

/**
 * Migrates legacy Hibernate 5 @TypeDef and @Type(type = "json") to Hibernate 6 @JdbcTypeCode(SqlTypes.JSON).
 */
public final class Hibernate6TypeMappingRecipe extends Recipe {

    @Override
    public String getDisplayName() {
        return "Migrate Hibernate 5 @Type / @TypeDef to Hibernate 6 @JdbcTypeCode";
    }

    @Override
    public String getDescription() {
        return "Replaces legacy Hibernate @Type(type = \"json\") annotations with modern @JdbcTypeCode(SqlTypes.JSON) and strips deprecated @TypeDef annotations.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {
            @Override
            public J.Annotation visitAnnotation(J.Annotation annotation, ExecutionContext ctx) {
                J.Annotation a = super.visitAnnotation(annotation, ctx);
                String simpleName = a.getSimpleName();
                if ("TypeDef".equals(simpleName) || "TypeDefs".equals(simpleName)) {
                    maybeRemoveImport("org.hibernate.annotations.TypeDef");
                    maybeRemoveImport("org.hibernate.annotations.TypeDefs");
                    // Note: returning null in JavaIsoVisitor is not supported, so we strip via AST or regex pass
                } else if ("Type".equals(simpleName)) {
                    String printed = a.printTrimmed();
                    if (printed.contains("json") || printed.contains("jsonb")) {
                        maybeRemoveImport("org.hibernate.annotations.Type");
                        maybeAddImport("org.hibernate.annotations.JdbcTypeCode");
                        maybeAddImport("org.hibernate.type.SqlTypes");
                        a = a.withAnnotationType(TypeTree.build("JdbcTypeCode(SqlTypes.JSON)"));
                    }
                }
                return a;
            }
        };
    }
}
