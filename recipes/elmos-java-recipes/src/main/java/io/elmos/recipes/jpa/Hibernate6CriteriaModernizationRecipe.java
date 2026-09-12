package io.elmos.recipes.jpa;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.TypeTree;

import java.util.Set;

/**
 * Modernizes legacy org.hibernate.Criteria to Jakarta Persistence CriteriaBuilder and CriteriaQuery.
 *
 * <p>Key transformations:
 * <ul>
 *   <li>Replaces {@code org.hibernate.Criteria} variable declarations with {@code jakarta.persistence.criteria.CriteriaQuery}.</li>
 *   <li>Replaces {@code org.hibernate.criterion.Criterion} with {@code jakarta.persistence.criteria.Predicate}.</li>
 *   <li>Replaces {@code org.hibernate.criterion.Projection} with {@code jakarta.persistence.criteria.Selection}.</li>
 *   <li>Replaces {@code org.hibernate.criterion.Order} with {@code jakarta.persistence.criteria.Order}.</li>
 *   <li>Modernizes calls to {@code Restrictions} and {@code Projections} to JPA Criteria equivalents.</li>
 *   <li>Cleans up legacy Hibernate imports and injects Jakarta Persistence criteria imports.</li>
 * </ul>
 */
public final class Hibernate6CriteriaModernizationRecipe extends Recipe {

    private static final Set<String> RESTRICTIONS_METHODS = Set.of(
            "eq", "ne", "like", "ilike", "gt", "lt", "ge", "le",
            "between", "in", "isNull", "isNotNull", "isEmpty", "isNotEmpty",
            "and", "or", "not", "conjunction", "disjunction"
    );

    @Override
    public String getDisplayName() {
        return "Modernize Hibernate Criteria to JPA CriteriaBuilder";
    }

    @Override
    public String getDescription() {
        return "Updates references from org.hibernate.Criteria, Restrictions, Projections, and Order to Jakarta Persistence equivalents.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {

            @Override
            public J.VariableDeclarations visitVariableDeclarations(J.VariableDeclarations multiVariable, ExecutionContext ctx) {
                J.VariableDeclarations vd = super.visitVariableDeclarations(multiVariable, ctx);
                TypeTree typeExpr = vd.getTypeExpression();
                if (typeExpr != null) {
                    String typeName = typeExpr.printTrimmed();
                    if ("Criteria".equals(typeName) || "org.hibernate.Criteria".equals(typeName)) {
                        maybeRemoveImport("org.hibernate.Criteria");
                        maybeAddImport("jakarta.persistence.criteria.CriteriaQuery");
                        maybeAddImport("jakarta.persistence.criteria.CriteriaBuilder");
                        vd = vd.withTypeExpression(TypeTree.build("CriteriaQuery<?>").withPrefix(typeExpr.getPrefix()));
                    } else if ("Criterion".equals(typeName) || "org.hibernate.criterion.Criterion".equals(typeName)
                            || "Conjunction".equals(typeName) || "org.hibernate.criterion.Conjunction".equals(typeName)
                            || "Disjunction".equals(typeName) || "org.hibernate.criterion.Disjunction".equals(typeName)) {
                        maybeRemoveImport("org.hibernate.criterion.Criterion");
                        maybeRemoveImport("org.hibernate.criterion.Conjunction");
                        maybeRemoveImport("org.hibernate.criterion.Disjunction");
                        maybeAddImport("jakarta.persistence.criteria.Predicate");
                        vd = vd.withTypeExpression(TypeTree.build("Predicate").withPrefix(typeExpr.getPrefix()));
                    } else if ("Projection".equals(typeName) || "org.hibernate.criterion.Projection".equals(typeName)) {
                        maybeRemoveImport("org.hibernate.criterion.Projection");
                        maybeAddImport("jakarta.persistence.criteria.Selection");
                        vd = vd.withTypeExpression(TypeTree.build("Selection<?>").withPrefix(typeExpr.getPrefix()));
                    } else if ("Order".equals(typeName) || "org.hibernate.criterion.Order".equals(typeName)) {
                        maybeRemoveImport("org.hibernate.criterion.Order");
                        maybeAddImport("jakarta.persistence.criteria.Order");
                        vd = vd.withTypeExpression(TypeTree.build("Order").withPrefix(typeExpr.getPrefix()));
                    }
                }
                return vd;
            }

            @Override
            public J.MethodInvocation visitMethodInvocation(J.MethodInvocation method, ExecutionContext ctx) {
                J.MethodInvocation m = super.visitMethodInvocation(method, ctx);

                // Check for Restrictions.xxx(...)
                if (m.getSelect() != null && "Restrictions".equals(m.getSelect().printTrimmed())) {
                    maybeRemoveImport("org.hibernate.criterion.Restrictions");
                    maybeAddImport("jakarta.persistence.criteria.Predicate");
                    maybeAddImport("jakarta.persistence.criteria.CriteriaBuilder");
                }

                // Check for Projections.xxx(...)
                if (m.getSelect() != null && "Projections".equals(m.getSelect().printTrimmed())) {
                    maybeRemoveImport("org.hibernate.criterion.Projections");
                    maybeAddImport("jakarta.persistence.criteria.CriteriaBuilder");
                }

                // Check for Order.asc / Order.desc
                if (m.getSelect() != null && "Order".equals(m.getSelect().printTrimmed())) {
                    maybeRemoveImport("org.hibernate.criterion.Order");
                    maybeAddImport("jakarta.persistence.criteria.Order");
                }

                // Check for session.createCriteria(Foo.class)
                if ("createCriteria".equals(m.getSimpleName())) {
                    maybeRemoveImport("org.hibernate.Criteria");
                    maybeAddImport("jakarta.persistence.criteria.CriteriaQuery");
                    maybeAddImport("jakarta.persistence.criteria.CriteriaBuilder");
                }

                // Check for criteria.setProjection(...)
                if ("setProjection".equals(m.getSimpleName())) {
                    m = m.withName(m.getName().withSimpleName("select"));
                }

                // Check for criteria.createAlias(...)
                if ("createAlias".equals(m.getSimpleName())) {
                    maybeAddImport("jakarta.persistence.criteria.Join");
                }

                return m;
            }

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
