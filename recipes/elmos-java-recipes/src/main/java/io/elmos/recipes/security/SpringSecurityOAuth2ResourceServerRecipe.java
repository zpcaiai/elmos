package io.elmos.recipes.security;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.TypeTree;

/**
 * Modernizes legacy OAuth2 resource server configurations to Spring Security 6+ Lambda DSL:
 * - {@code @EnableResourceServer} -> {@code @Configuration}
 * - {@code http.oauth2ResourceServer().jwt()} -> {@code http.oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))}.
 */
public final class SpringSecurityOAuth2ResourceServerRecipe extends Recipe {

    @Override
    public String getDisplayName() {
        return "Modernize OAuth2 Resource Server to Spring Security 6+ Lambda DSL";
    }

    @Override
    public String getDescription() {
        return "Converts legacy @EnableResourceServer and chained oauth2ResourceServer() calls into the modern pattern.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {
            @Override
            public J.Annotation visitAnnotation(J.Annotation annotation, ExecutionContext ctx) {
                J.Annotation a = super.visitAnnotation(annotation, ctx);
                if ("EnableResourceServer".equals(a.getSimpleName())) {
                    maybeRemoveImport("org.springframework.security.oauth2.config.annotation.web.configuration.EnableResourceServer");
                    maybeAddImport("org.springframework.context.annotation.Configuration");
                    a = a.withAnnotationType(TypeTree.build("Configuration"));
                }
                return a;
            }

            @Override
            public J.Import visitImport(J.Import _import, ExecutionContext ctx) {
                J.Import imp = super.visitImport(_import, ctx);
                String typeName = imp.getQualid().printTrimmed();
                if (typeName.contains("EnableResourceServer")) {
                    imp = imp.withQualid(TypeTree.build("org.springframework.context.annotation.Configuration"));
                }
                return imp;
            }

            private boolean isNoArg(J.MethodInvocation inv) {
                return inv.getArguments().isEmpty() ||
                       (inv.getArguments().size() == 1 && inv.getArguments().get(0) instanceof J.Empty);
            }

            @Override
            public J.MethodInvocation visitMethodInvocation(J.MethodInvocation method, ExecutionContext ctx) {
                J.MethodInvocation m = super.visitMethodInvocation(method, ctx);
                if ("jwt".equals(m.getSimpleName()) && m.getSelect() instanceof J.MethodInvocation sel && "oauth2ResourceServer".equals(sel.getSimpleName()) && isNoArg(sel)) {
                    maybeAddImport("org.springframework.security.config.Customizer");
                    org.openrewrite.java.JavaParser jp = org.openrewrite.java.JavaParser.fromJavaVersion().build();
                    var parsed = jp.parse("""
                            import org.springframework.security.config.Customizer;
                            class _T {
                                void f(org.springframework.security.config.annotation.web.builders.HttpSecurity http) throws Exception {
                                    http.oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
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
