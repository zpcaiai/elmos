package io.elmos.recipes.security;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.TypeTree;

import java.util.Set;

/**
 * OpenRewrite recipe to modernize legacy Spring Security configurations to Spring Security 6 / Boot 3+.
 *
 * <p>Key transformations:
 * <ol>
 *   <li>Removes {@code extends WebSecurityConfigurerAdapter}.</li>
 *   <li>Migrates {@code protected void configure(HttpSecurity http)} to {@code @Bean public SecurityFilterChain filterChain(HttpSecurity http) throws Exception}.</li>
 *   <li>Replaces {@code authorizeRequests()} with {@code authorizeHttpRequests()}.</li>
 *   <li>Replaces {@code antMatchers(...)} with {@code requestMatchers(...)}.</li>
 *   <li>Removes obsolete {@code and()} chained calls in HttpSecurity configuration.</li>
 * </ol>
 */
public final class SpringSecurityFilterChainRecipe extends Recipe {

    private static final String WEB_SECURITY_ADAPTER = "WebSecurityConfigurerAdapter";
    private static final Set<String> MATCHERS_METHODS = Set.of("antMatchers", "mvcMatchers", "regexMatchers");

    @Override
    public String getDisplayName() {
        return "Modernize Spring Security Filter Chain to Spring Security 6+";
    }

    @Override
    public String getDescription() {
        return "Converts WebSecurityConfigurerAdapter and authorizeRequests() chains into modern SecurityFilterChain bean definitions.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {

            @Override
            public J.Annotation visitAnnotation(J.Annotation annotation, ExecutionContext ctx) {
                J.Annotation a = super.visitAnnotation(annotation, ctx);
                if ("EnableGlobalMethodSecurity".equals(a.getSimpleName())) {
                    maybeRemoveImport("org.springframework.security.config.annotation.method.configuration.EnableGlobalMethodSecurity");
                    maybeAddImport("org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity");
                    a = a.withAnnotationType(TypeTree.build("EnableMethodSecurity"));
                }
                return a;
            }

            @Override
            public J.ClassDeclaration visitClassDeclaration(J.ClassDeclaration classDecl, ExecutionContext ctx) {
                J.ClassDeclaration c = super.visitClassDeclaration(classDecl, ctx);
                TypeTree extendsClause = c.getExtends();
                if (extendsClause != null && extendsClause.printTrimmed().contains(WEB_SECURITY_ADAPTER)) {
                    maybeRemoveImport("org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter");
                    maybeAddImport("org.springframework.context.annotation.Bean");
                    maybeAddImport("org.springframework.context.annotation.Configuration");
                    maybeAddImport("org.springframework.security.web.SecurityFilterChain");
                    maybeAddImport("org.springframework.security.config.annotation.web.builders.HttpSecurity");
                    c = c.withExtends(null);
                }
                return c;
            }

            @Override
            public J.MethodDeclaration visitMethodDeclaration(J.MethodDeclaration method, ExecutionContext ctx) {
                J.MethodDeclaration m = super.visitMethodDeclaration(method, ctx);
                if ("configure".equals(m.getSimpleName()) && m.getParameters().size() == 1) {
                    String paramType = m.getParameters().get(0).printTrimmed();
                    if (paramType.contains("HttpSecurity")) {
                        maybeAddImport("org.springframework.context.annotation.Bean");
                        maybeAddImport("org.springframework.security.web.SecurityFilterChain");
                        m = m.withReturnTypeExpression(TypeTree.build("SecurityFilterChain").withPrefix(
                                m.getReturnTypeExpression() != null ? m.getReturnTypeExpression().getPrefix() : org.openrewrite.java.tree.Space.format(" ")
                        ));
                        m = m.withName(m.getName().withSimpleName("filterChain"));

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

                        // Strip @Override and inject @Bean annotation if not present
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
                            J.Annotation beanAnn = new J.Annotation(
                                    org.openrewrite.Tree.randomId(),
                                    org.openrewrite.java.tree.Space.EMPTY,
                                    org.openrewrite.marker.Markers.EMPTY,
                                    TypeTree.build("Bean"),
                                    org.openrewrite.java.tree.JContainer.empty()
                            );
                            annotations.add(beanAnn);
                        }
                        m = m.withLeadingAnnotations(annotations);

                        // Ensure return <httpVar>.build();
                        if (m.getBody() != null) {
                            String httpVar = "http";
                            if (!m.getParameters().isEmpty()) {
                                String pStr = m.getParameters().get(0).printTrimmed();
                                String[] parts = pStr.split("\\s+");
                                if (parts.length > 1) {
                                    httpVar = parts[parts.length - 1];
                                }
                            }
                            boolean hasReturn = false;
                            for (org.openrewrite.java.tree.Statement stmt : m.getBody().getStatements()) {
                                if (stmt instanceof J.Return) {
                                    hasReturn = true;
                                    break;
                                }
                            }
                            if (!hasReturn) {
                                org.openrewrite.java.JavaParser jp = org.openrewrite.java.JavaParser.fromJavaVersion().build();
                                var parsed = jp.parse("class _T { SecurityFilterChain f() { return " + httpVar + ".build(); } }").findFirst().orElse(null);
                                if (parsed instanceof J.CompilationUnit cu && !cu.getClasses().isEmpty()) {
                                    J.ClassDeclaration cd = (J.ClassDeclaration) cu.getClasses().get(0);
                                    if (!cd.getBody().getStatements().isEmpty()) {
                                        J.MethodDeclaration md = (J.MethodDeclaration) cd.getBody().getStatements().get(0);
                                        if (!md.getBody().getStatements().isEmpty()) {
                                            org.openrewrite.java.tree.Statement retStmt = md.getBody().getStatements().get(0);
                                            java.util.List<org.openrewrite.java.tree.Statement> stmts = new java.util.ArrayList<>(m.getBody().getStatements());
                                            stmts.add(retStmt.withPrefix(org.openrewrite.java.tree.Space.format("\n        ")));
                                            m = m.withBody(m.getBody().withStatements(stmts));
                                        }
                                    }
                                }
                            }
                        }
                    } else if (paramType.contains("WebSecurity") && !paramType.contains("HttpSecurity")) {
                        maybeAddImport("org.springframework.context.annotation.Bean");
                        maybeAddImport("org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer");
                        m = m.withReturnTypeExpression(TypeTree.build("WebSecurityCustomizer").withPrefix(
                                m.getReturnTypeExpression() != null ? m.getReturnTypeExpression().getPrefix() : org.openrewrite.java.tree.Space.format(" ")
                        ));
                        m = m.withName(m.getName().withSimpleName("webSecurityCustomizer"));
                        m = m.withParameters(java.util.Collections.emptyList());

                        java.util.List<J.Annotation> annotations = new java.util.ArrayList<>();
                        boolean hasBean = false;
                        for (J.Annotation an : m.getLeadingAnnotations()) {
                            if (!"Override".equals(an.getSimpleName())) {
                                if ("Bean".equals(an.getSimpleName())) {
                                    hasBean = true;
                                }
                                annotations.add(an);
                            }
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
                    }
                }
                return m;
            }

            @Override
            public J.MethodInvocation visitMethodInvocation(J.MethodInvocation method, ExecutionContext ctx) {
                J.MethodInvocation m = super.visitMethodInvocation(method, ctx);
                if ("authorizeRequests".equals(m.getSimpleName())) {
                    m = m.withName(m.getName().withSimpleName("authorizeHttpRequests"));
                } else if (MATCHERS_METHODS.contains(m.getSimpleName())) {
                    m = m.withName(m.getName().withSimpleName("requestMatchers"));
                } else if ("and".equals(m.getSimpleName()) && (m.getArguments().isEmpty() || (m.getArguments().size() == 1 && m.getArguments().get(0) instanceof J.Empty)) && m.getSelect() instanceof J.MethodInvocation sel) {
                    m = sel;
                }
                return m;
            }
        };
    }
}
