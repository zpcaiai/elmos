package io.elmos.recipes.jpa;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.Expression;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.TypeTree;

import java.util.ArrayList;
import java.util.List;

/**
 * Modernizes legacy JPA Query annotations:
 * - {@code javax.persistence.NamedQuery} -> {@code jakarta.persistence.NamedQuery}
 * - Index unnumbered positional parameters {@code ?} -> {@code ?1, ?2} for Hibernate 6 SQM.
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
                String simpleName = a.getSimpleName();
                if ("NamedQuery".equals(simpleName) || "NamedQueries".equals(simpleName) ||
                    "NamedNativeQuery".equals(simpleName) || "NamedNativeQueries".equals(simpleName)) {
                    maybeRemoveImport("javax.persistence." + simpleName);
                    maybeAddImport("jakarta.persistence." + simpleName);
                }

                // Index unindexed positional parameters in @Query("...")
                if ("Query".equals(simpleName) && a.getArguments() != null) {
                    List<Expression> newArgs = new ArrayList<>();
                    boolean modified = false;
                    for (Expression arg : a.getArguments()) {
                        if (arg instanceof J.Literal lit && lit.getValue() instanceof String qStr) {
                            if (qStr.contains("?") && !qStr.matches(".*\\?\\d+.*")) {
                                String indexedQuery = indexPositionalParameters(qStr);
                                newArgs.add(lit.withValue(indexedQuery).withValueSource("\"" + indexedQuery.replace("\"", "\\\"") + "\""));
                                modified = true;
                                continue;
                            }
                        }
                        newArgs.add(arg);
                    }
                    if (modified) {
                        a = a.withArguments(newArgs);
                    }
                }
                return a;
            }

            private String indexPositionalParameters(String query) {
                StringBuilder sb = new StringBuilder();
                int paramIndex = 1;
                boolean inQuotes = false;
                for (int i = 0; i < query.length(); i++) {
                    char c = query.charAt(i);
                    if (c == '\'') {
                        inQuotes = !inQuotes;
                        sb.append(c);
                    } else if (c == '?' && !inQuotes) {
                        // Check if already followed by digit
                        if (i + 1 < query.length() && Character.isDigit(query.charAt(i + 1))) {
                            sb.append(c);
                        } else {
                            sb.append('?').append(paramIndex++);
                        }
                    } else {
                        sb.append(c);
                    }
                }
                return sb.toString();
            }
        };
    }
}
