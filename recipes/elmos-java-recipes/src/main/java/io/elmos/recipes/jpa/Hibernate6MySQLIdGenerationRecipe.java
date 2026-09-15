package io.elmos.recipes.jpa;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.Expression;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.TypeTree;

import java.util.Collections;
import java.util.List;

/**
 * OpenRewrite recipe to modernize JPA @GeneratedValue(strategy = GenerationType.AUTO) to GenerationType.IDENTITY for MySQL.
 *
 * <p>In Hibernate 5 with MySQL dialects, {@code GenerationType.AUTO} defaulted to {@code IDENTITY} (auto-increment).
 * In Hibernate 6, {@code GenerationType.AUTO} defaults to {@code SequenceStyleGenerator} using a sequence table
 * (e.g. {@code hibernate_sequence}), which fails at runtime on MySQL schemas unless manually created.
 *
 * <p>This recipe replaces {@code strategy = GenerationType.AUTO} (or unspecified default strategy) with
 * {@code strategy = GenerationType.IDENTITY}.
 */
public final class Hibernate6MySQLIdGenerationRecipe extends Recipe {

    @Override
    public String getDisplayName() {
        return "Modernize MySQL JPA GenerationType.AUTO to GenerationType.IDENTITY";
    }

    @Override
    public String getDescription() {
        return "Replaces GenerationType.AUTO with GenerationType.IDENTITY to prevent Hibernate 6 hibernate_sequence table errors on MySQL.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {
            @Override
            public J.Annotation visitAnnotation(J.Annotation annotation, ExecutionContext ctx) {
                J.Annotation a = super.visitAnnotation(annotation, ctx);
                if ("GeneratedValue".equals(a.getSimpleName())) {
                    String printed = a.printTrimmed();
                    if (!printed.contains("IDENTITY") && !printed.contains("SEQUENCE") && !printed.contains("TABLE") && !printed.contains("UUID")) {
                        maybeAddImport("jakarta.persistence.GenerationType");
                        if (a.getArguments() == null || a.getArguments().isEmpty()) {
                            a = a.withArguments(Collections.singletonList(
                                    TypeTree.build("strategy = GenerationType.IDENTITY")
                            ));
                        } else {
                            List<Expression> updatedArgs = a.getArguments().stream()
                                    .map(arg -> {
                                        if (arg instanceof J.Assignment assign) {
                                            if (assign.getAssignment().printTrimmed().contains("AUTO")) {
                                                return (Expression) assign.withAssignment(TypeTree.build("GenerationType.IDENTITY"));
                                            }
                                        }
                                        return arg;
                                    })
                                    .toList();
                            a = a.withArguments(updatedArgs);
                        }
                    }
                }
                return a;
            }
        };
    }
}
