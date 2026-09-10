package io.elmos.recipes.jpa;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.TypeTree;

/**
 * Modernizes legacy JPA Query annotations:
 * - {@code javax.persistence.NamedQuery} -> {@code jakarta.persistence.NamedQuery}
 * - {@code javax.persistence.Query} -> {@code jakarta.persistence.Query}
 */
public final class SpringDataJpaNamedQueryModernizationRecipe extends Recipe {

    @Override
    public String getDisplayName() {
        return "Modernize JPA Named Queries and Repository Query contracts";
    }

    @Override
    public String getDescription() {
        return "Replaces legacy javax.persistence Query/NamedQuery annotations and normalizes parameter contracts for Hibernate 6/SQM.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {
            @Override
            public J.Import visitImport(J.Import _import, ExecutionContext ctx) {
                J.Import imp = super.visitImport(_import, ctx);
                String typeName = imp.getQualid().printTrimmed();
                if (typeName.startsWith("javax.persistence")) {
                    String newName = typeName.replace("javax.persistence", "jakarta.persistence");
                    imp = imp.withQualid(TypeTree.build(newName));
                }
                return imp;
            }

            @Override
            public J.Annotation visitAnnotation(J.Annotation annotation, ExecutionContext ctx) {
                J.Annotation a = super.visitAnnotation(annotation, ctx);
                if ("NamedQuery".equals(a.getSimpleName()) || "NamedQueries".equals(a.getSimpleName()) ||
                    "NamedNativeQuery".equals(a.getSimpleName()) || "NamedNativeQueries".equals(a.getSimpleName())) {
                    maybeRemoveImport("javax.persistence." + a.getSimpleName());
                    maybeAddImport("jakarta.persistence." + a.getSimpleName());
                }
                return a;
            }
        };
    }
}
