package io.elmos.recipes;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.Expression;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.TypeTree;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;

/**
 * Repairs the structural boundary introduced when Spring Security's legacy
 * builder chain is converted to the lambda DSL.
 *
 * <p>The upstream conversion can leave calls after {@code and()} inside the
 * authorization lambda. Those calls belong to {@code HttpSecurity}, not to
 * {@code AuthorizationManagerRequestMatcherRegistry}; keeping them in the
 * lambda produces a target compile failure. This visitor moves only the
 * invocation suffix after an explicit zero-argument {@code and()} back onto
 * the outer {@code authorizeRequests} / {@code authorizeHttpRequests} call.
 * It is deliberately AST-based and does not rewrite arbitrary text.</p>
 */
public final class SpringSecurityLambdaChain extends Recipe {
    private static final Set<String> AUTHORIZATION_METHODS = Set.of(
            "authorizeRequests", "authorizeHttpRequests");

    @Override
    public String getDisplayName() {
        return "Normalize Spring Security authorization lambda chains";
    }

    @Override
    public String getDescription() {
        return "Normalizes Spring Security DSL chains and checked-exception signatures "
                + "after a Spring Security migration.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {
            @Override
            public J.Try.Catch visitCatch(J.Try.Catch catchBlock, ExecutionContext ctx) {
                J.Try.Catch visited = super.visitCatch(catchBlock, ctx);
                J.VariableDeclarations declarations = visited.getParameter().getTree();
                if (declarations == null || declarations.getTypeExpression() == null
                        || !isJacksonException(declarations.getTypeExpression())) {
                    return visited;
                }
                maybeRemoveImport("tools.jackson.core.JacksonException");
                maybeAddImport("java.io.IOException");
                return visited.withParameter(visited.getParameter().withTree(
                        declarations.withTypeExpression(TypeTree.build("IOException"))));
            }

            @Override
            public J.MethodInvocation visitMethodInvocation(
                    J.MethodInvocation method, ExecutionContext ctx) {
                J.MethodInvocation visited = super.visitMethodInvocation(method, ctx);
                if (!AUTHORIZATION_METHODS.contains(visited.getSimpleName())
                        || visited.getArguments().size() != 1
                        || !(visited.getArguments().get(0) instanceof J.Lambda lambda)
                        || !(lambda.getBody() instanceof J.MethodInvocation lambdaRoot)) {
                    return visited;
                }

                AndBoundary boundary = findAndBoundary(lambdaRoot);
                if (boundary == null) {
                    return visited;
                }

                J.Lambda normalizedLambda = lambda.withBody(boundary.authorizationChain());
                J.MethodInvocation normalizedAuthorization = visited.withArguments(
                        List.of(normalizedLambda));

                Expression rebuilt = normalizedAuthorization;
                for (int index = boundary.suffix().size() - 1; index >= 0; index--) {
                    rebuilt = boundary.suffix().get(index).withSelect(rebuilt);
                }
                return (J.MethodInvocation) rebuilt;
            }
        };
    }

    private static boolean isJacksonException(TypeTree type) {
        String name = type.printTrimmed();
        return name.equals("JacksonException") || name.endsWith(".JacksonException");
    }

    private static AndBoundary findAndBoundary(J.MethodInvocation root) {
        List<J.MethodInvocation> suffix = new ArrayList<>();
        J.MethodInvocation current = root;
        while (true) {
            if ("and".equals(current.getSimpleName())
                    && isNoArgumentInvocation(current)
                    && current.getSelect() instanceof Expression authorizationChain) {
                return new AndBoundary(authorizationChain, List.copyOf(suffix));
            }
            suffix.add(current);
            if (!(current.getSelect() instanceof J.MethodInvocation selected)) {
                return null;
            }
            current = selected;
        }
    }

    private static boolean isNoArgumentInvocation(J.MethodInvocation method) {
        return method.getArguments().isEmpty()
                || (method.getArguments().size() == 1
                && method.getArguments().get(0) instanceof J.Empty);
    }

    private record AndBoundary(Expression authorizationChain,
                               List<J.MethodInvocation> suffix) {
    }
}
