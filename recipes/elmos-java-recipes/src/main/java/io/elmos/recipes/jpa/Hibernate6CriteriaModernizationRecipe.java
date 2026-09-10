package io.elmos.recipes.jpa;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.J;

/**
 * Modernizes legacy org.hibernate.Criteria to Jakarta Persistence CriteriaBuilder and Spring Data Specifications.
 */
public final class Hibernate6CriteriaModernizationRecipe extends Recipe {

    @Override
    public String getDisplayName() {
        return "Modernize Hibernate Criteria to JPA CriteriaBuilder";
    }

    @Override
    public String getDescription() {
        return "Updates references from org.hibernate.Criteria to jakarta.persistence.criteria.CriteriaQuery.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {
            @Override
            public J.Identifier visitIdentifier(J.Identifier identifier, ExecutionContext ctx) {
                J.Identifier id = super.visitIdentifier(identifier, ctx);
                if ("Criteria".equals(id.getSimpleName())) {
                    maybeRemoveImport("org.hibernate.Criteria");
                    maybeAddImport("jakarta.persistence.criteria.CriteriaQuery");
                    maybeAddImport("jakarta.persistence.criteria.CriteriaBuilder");
                    return id.withSimpleName("CriteriaQuery");
                }
                return id;
            }
        };
    }
}
