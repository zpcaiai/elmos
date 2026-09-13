package io.elmos.recipes.security;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.J;

/**
 * Modernizes sessionManagement() chained configuration to SessionCreationPolicy lambda.
 */
public final class SpringSecuritySessionManagementRecipe extends Recipe {

    @Override
    public String getDisplayName() {
        return "Modernize Session Management Lambda Configuration";
    }

    @Override
    public String getDescription() {
        return "Converts legacy sessionManagement().sessionCreationPolicy(...) to sessionManagement(s -> s.sessionCreationPolicy(...)).";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {
            private boolean isNoArg(J.MethodInvocation inv) {
                return inv.getArguments().isEmpty() ||
                       (inv.getArguments().size() == 1 && inv.getArguments().get(0) instanceof J.Empty);
            }

            @Override
            public J.MethodInvocation visitMethodInvocation(J.MethodInvocation method, ExecutionContext ctx) {
                J.MethodInvocation m = super.visitMethodInvocation(method, ctx);
                if (m.getSelect() instanceof J.MethodInvocation sel && "sessionManagement".equals(sel.getSimpleName()) && isNoArg(sel)) {
                    maybeAddImport("org.springframework.security.config.http.SessionCreationPolicy");
                    String innerMethod = m.getSimpleName();
                    String argStr = "";
                    if (!m.getArguments().isEmpty() && !(m.getArguments().size() == 1 && m.getArguments().get(0) instanceof J.Empty)) {
                        argStr = m.getArguments().get(0).printTrimmed();
                    }
                    org.openrewrite.java.JavaParser jp = org.openrewrite.java.JavaParser.fromJavaVersion().build();
                    var parsed = jp.parse("""
                            class _T {
                                void f(org.springframework.security.config.annotation.web.builders.HttpSecurity http) throws Exception {
                                    http.sessionManagement(session -> session.""" + innerMethod + "(" + argStr + "));\n"
                            + """
                                }
                            }
                            """).findFirst().orElse(null);
                    if (parsed instanceof J.CompilationUnit cu && !cu.getClasses().isEmpty()) {
                        J.ClassDeclaration cd = (J.ClassDeclaration) cu.getClasses().get(0);
                        J.MethodDeclaration md = (J.MethodDeclaration) cd.getBody().getStatements().get(0);
                        J.MethodInvocation replacement = (J.MethodInvocation) md.getBody().getStatements().get(0);
                        return replacement.withSelect(sel.getSelect()).withPrefix(sel.getPrefix());
                    }
                }
                return m;
            }
        };
    }
}
