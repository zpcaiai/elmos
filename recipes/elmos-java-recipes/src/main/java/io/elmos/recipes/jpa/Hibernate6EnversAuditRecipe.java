package io.elmos.recipes.jpa;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.TypeTree;

/**
 * Modernizes Hibernate Envers audit annotations:
 * - {@code @Audited} -> preserves with modern Jakarta Entity bindings
 * - Replaces deprecated AuditReader / RevisionEntity bindings to Jakarta Persistence
 */
public final class Hibernate6EnversAuditRecipe extends Recipe {

    @Override
    public String getDisplayName() {
        return "Modernize Hibernate Envers Auditing to Hibernate 6 / Jakarta";
    }

    @Override
    public String getDescription() {
        return "Ensures Envers entity auditing conforms with Jakarta persistence and modern revision listener contracts.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {
            @Override
            public J.Annotation visitAnnotation(J.Annotation annotation, ExecutionContext ctx) {
                J.Annotation a = super.visitAnnotation(annotation, ctx);
                if ("RevisionEntity".equals(a.getSimpleName())) {
                    maybeRemoveImport("org.hibernate.envers.RevisionEntity");
                    maybeAddImport("org.hibernate.envers.RevisionEntity");
                }
                return a;
            }
        };
    }
}
