package io.elmos.recipes.security;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.TypeTree;

/**
 * Modernizes AuthenticationManagerBuilder configuration to @Bean AuthenticationManager in Spring Security 6+.
 */
public final class SpringSecurityAuthenticationRecipe extends Recipe {

    @Override
    public String getDisplayName() {
        return "Modernize AuthenticationManagerBuilder to AuthenticationManager @Bean";
    }

    @Override
    public String getDescription() {
        return "Converts configure(AuthenticationManagerBuilder auth) methods into modern @Bean AuthenticationManager declarations.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {
            @Override
            public J.MethodDeclaration visitMethodDeclaration(J.MethodDeclaration method, ExecutionContext ctx) {
                J.MethodDeclaration m = super.visitMethodDeclaration(method, ctx);
                if ("configure".equals(m.getSimpleName()) && m.getParameters().size() == 1) {
                    String paramType = m.getParameters().get(0).printTrimmed();
                    if (paramType.contains("AuthenticationManagerBuilder")) {
                        maybeRemoveImport("org.springframework.security.config.annotation.authentication.builders.AuthenticationManagerBuilder");
                        maybeAddImport("org.springframework.context.annotation.Bean");
                        maybeAddImport("org.springframework.security.authentication.AuthenticationManager");
                        maybeAddImport("org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration");
                        m = m.withReturnTypeExpression(TypeTree.build("AuthenticationManager").withPrefix(
                                m.getReturnTypeExpression() != null ? m.getReturnTypeExpression().getPrefix() : org.openrewrite.java.tree.Space.format(" ")
                        ));
                        m = m.withName(m.getName().withSimpleName("authenticationManager"));

                        // Strip @Override and inject @Bean
                        java.util.List<J.Annotation> annotations = new java.util.ArrayList<>();
                        boolean hasBean = false;
                        for (J.Annotation an : m.getLeadingAnnotations()) {
                            if ("Override".equals(an.getSimpleName())) {
                                continue;
                            }
                            if ("Bean".equals(an.getSimpleName())) {
                                hasBean = true;
                            }
                            annotations.add(an);
                        }
                        if (!hasBean) {
                            annotations.add(new J.Annotation(
                                    org.openrewrite.Tree.randomId(),
                                    org.openrewrite.java.tree.Space.EMPTY,
                                    org.openrewrite.marker.Markers.EMPTY,
                                    TypeTree.build("Bean"),
                                    org.openrewrite.java.tree.JContainer.empty()
                            ));
                        }
                        m = m.withLeadingAnnotations(annotations);

                        // Ensure 'public' modifier
                        java.util.List<J.Modifier> modifiers = new java.util.ArrayList<>();
                        boolean hasPublic = false;
                        for (J.Modifier mod : m.getModifiers()) {
                            if (mod.getType() == J.Modifier.Type.Protected) {
                                modifiers.add(new J.Modifier(
                                        mod.getId(),
                                        mod.getPrefix(),
                                        mod.getMarkers(),
                                        "public",
                                        J.Modifier.Type.Public,
                                        mod.getAnnotations()
                                ));
                                hasPublic = true;
                            } else if (mod.getType() == J.Modifier.Type.Public) {
                                modifiers.add(mod);
                                hasPublic = true;
                            } else {
                                modifiers.add(mod);
                            }
                        }
                        if (!hasPublic) {
                            modifiers.add(0, new J.Modifier(
                                    org.openrewrite.Tree.randomId(),
                                    org.openrewrite.java.tree.Space.EMPTY,
                                    org.openrewrite.marker.Markers.EMPTY,
                                    "public",
                                    J.Modifier.Type.Public,
                                    java.util.Collections.emptyList()
                            ));
                        }
                        m = m.withModifiers(modifiers);

                        // Replace parameter & body using JavaParser
                        org.openrewrite.java.JavaParser jp = org.openrewrite.java.JavaParser.fromJavaVersion().build();
                        var parsed = jp.parse("""
                                class _T {
                                    AuthenticationManager authenticationManager(AuthenticationConfiguration authenticationConfiguration) throws Exception {
                                        return authenticationConfiguration.getAuthenticationManager();
                                    }
                                }
                                """).findFirst().orElse(null);
                        if (parsed instanceof J.CompilationUnit cu && !cu.getClasses().isEmpty()) {
                            J.ClassDeclaration cd = (J.ClassDeclaration) cu.getClasses().get(0);
                            if (!cd.getBody().getStatements().isEmpty()) {
                                J.MethodDeclaration md = (J.MethodDeclaration) cd.getBody().getStatements().get(0);
                                m = m.withParameters(md.getParameters());
                                m = m.withBody(md.getBody());
                            }
                        }
                    }
                }
                return m;
            }
        };
    }
}
