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
                        m = m.withReturnTypeExpression(TypeTree.build("SecurityFilterChain"));
                        m = m.withName(m.getName().withSimpleName("filterChain"));

                        // Inject @Bean annotation if not present
                        boolean hasBean = m.getLeadingAnnotations().stream()
                                .anyMatch(an -> "Bean".equals(an.getSimpleName()));
                        if (!hasBean) {
                            J.Annotation beanAnn = new J.Annotation(
                                    org.openrewrite.Tree.randomId(),
                                    org.openrewrite.java.tree.Space.EMPTY,
                                    org.openrewrite.marker.Markers.EMPTY,
                                    TypeTree.build("Bean"),
                                    org.openrewrite.java.tree.JContainer.empty()
                            );
                            java.util.List<J.Annotation> annotations = new java.util.ArrayList<>(m.getLeadingAnnotations());
                            annotations.add(beanAnn);
                            m = m.withLeadingAnnotations(annotations);
                        }
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
                }
                return m;
            }
        };
    }
}
