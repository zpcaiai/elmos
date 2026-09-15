package io.elmos.worker.rewrite;

import io.elmos.recipes.cloud.*;
import io.elmos.recipes.jpa.*;
import io.elmos.recipes.security.*;
import io.elmos.recipes.transaction.*;
import io.elmos.recipes.web.*;
import io.elmos.recipes.xml.*;
import org.openrewrite.ExecutionContext;
import org.openrewrite.InMemoryExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.SourceFile;
import org.openrewrite.java.JavaParser;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

/**
 * Industrial-grade Compiler-level AST Modernization Engine based on OpenRewrite.
 *
 * <p>Completely eliminates heuristic string/regex transformations by compiling Java
 * source code into strongly typed Abstract Syntax Tree (J) structures and applying
 * formal tree visitors with full type-attribution, formatting preservation, and import hygiene.
 */
public final class OpenRewriteAstCompiler {

    private OpenRewriteAstCompiler() {}

    public record AstRewriteResult(
            boolean modified,
            String source,
            List<String> recipesApplied
    ) {
        public static AstRewriteResult unmodified(String source) {
            return new AstRewriteResult(false, source, Collections.emptyList());
        }
    }

    /**
     * Executes a pipeline of OpenRewrite recipes against Java source code.
     *
     * @param sourceCode raw Java source code
     * @param recipes    list of OpenRewrite recipes to apply in sequence
     * @return transformed source code and audit record of recipes applied
     */
    public static AstRewriteResult rewrite(String sourceCode, List<Recipe> recipes) {
        Objects.requireNonNull(sourceCode, "sourceCode must not be null");
        if (recipes == null || recipes.isEmpty()) {
            return AstRewriteResult.unmodified(sourceCode);
        }

        try {
            SourceFile ast = JavaParser.fromJavaVersion()
                    .build()
                    .parse(sourceCode)
                    .findFirst()
                    .orElse(null);

            if (ast == null) {
                return AstRewriteResult.unmodified(sourceCode);
            }

            ExecutionContext ctx = new InMemoryExecutionContext(t -> {});
            List<String> applied = new ArrayList<>();
            SourceFile current = ast;

            for (Recipe recipe : recipes) {
                try {
                    var run = recipe.run(new org.openrewrite.internal.InMemoryLargeSourceSet(List.of(current)), ctx);
                    var results = run.getChangeset().getAllResults();
                    if (!results.isEmpty() && results.get(0).getAfter() != null) {
                        current = results.get(0).getAfter();
                        applied.add(recipe.getName() != null && !recipe.getName().isBlank()
                                ? recipe.getName()
                                : recipe.getClass().getSimpleName());
                    } else {
                        SourceFile next = (SourceFile) recipe.getVisitor().visit(current, ctx);
                        if (next != null && next != current) {
                            current = next;
                            applied.add(recipe.getName() != null && !recipe.getName().isBlank()
                                    ? recipe.getName()
                                    : recipe.getClass().getSimpleName());
                        }
                    }
                } catch (Exception e) {
                    try {
                        SourceFile next = (SourceFile) recipe.getVisitor().visit(current, ctx);
                        if (next != null && next != current) {
                            current = next;
                            applied.add(recipe.getName() != null && !recipe.getName().isBlank()
                                    ? recipe.getName()
                                    : recipe.getClass().getSimpleName());
                        }
                    } catch (Exception ignored) {
                        // Fail-safe per recipe to ensure pipeline resilience
                    }
                }
            }

            String rewritten = current.printAll();
            boolean modified = !rewritten.equals(sourceCode);
            return new AstRewriteResult(modified, rewritten, Collections.unmodifiableList(applied));
        } catch (Exception e) {
            // Parser fallback: return unmodified source if syntax is unparseable
            return AstRewriteResult.unmodified(sourceCode);
        }
    }

    /**
     * Modernizes Spring Security 5/Boot 2 configurations to Spring Security 6 / Boot 3
     * using the official OpenRewrite typed AST recipes.
     */
    public static AstRewriteResult modernizeSecurity(String sourceCode) {
        if (!sourceCode.contains("WebSecurityConfigurerAdapter")
                && !sourceCode.contains("authorizeRequests")
                && !sourceCode.contains("EnableGlobalMethodSecurity")
                && !sourceCode.contains("antMatchers")) {
            return AstRewriteResult.unmodified(sourceCode);
        }

        return rewrite(sourceCode, List.of(
                new SpringSecurityFilterChainRecipe(),
                new SpringSecurityCorsConfigurationRecipe(),
                new SpringSecurityCsrfCookieRepositoryRecipe(),
                new SpringSecurityMethodSecurityRecipe(),
                new SpringSecurityOAuth2ResourceServerRecipe(),
                new SpringSecuritySessionManagementRecipe(),
                new SpringSecurityCustomFilterOrderRecipe()
        ));
    }

    /**
     * Modernizes Hibernate 3/4/5 legacy Criteria, TypeDefs, named queries, and MySQL ID generation to
     * Jakarta Persistence 3.x / Hibernate 6 using OpenRewrite typed AST recipes.
     */
    public static AstRewriteResult modernizeJpaHibernate(String sourceCode) {
        if (!sourceCode.contains("org.hibernate.Criteria")
                && !sourceCode.contains("org.hibernate.criterion")
                && !sourceCode.contains("Restrictions")
                && !sourceCode.contains("Projections")
                && !sourceCode.contains("@TypeDef")
                && !sourceCode.contains("TypeDefinition")
                && !sourceCode.contains("GenerationType.AUTO")) {
            return AstRewriteResult.unmodified(sourceCode);
        }

        return rewrite(sourceCode, List.of(
                new Hibernate6CriteriaModernizationRecipe(),
                new Hibernate6TypeMappingRecipe(),
                new Hibernate6DialectFunctionRecipe(),
                new Hibernate6EnversAuditRecipe(),
                new SpringDataJpaNamedQueryModernizationRecipe(),
                new Hibernate6MySQLIdGenerationRecipe()
        ));
    }

    /**
     * Modernizes Spring Web MVC deprecated classes (WebMvcConfigurerAdapter, HandlerInterceptorAdapter)
     * to modern interface implementations.
     */
    public static AstRewriteResult modernizeWebMvc(String sourceCode) {
        if (!sourceCode.contains("WebMvcConfigurerAdapter")
                && !sourceCode.contains("HandlerInterceptorAdapter")) {
            return AstRewriteResult.unmodified(sourceCode);
        }

        return rewrite(sourceCode, List.of(
                new SpringWebMvcConfigurerAdapterRecipe(),
                new SpringHandlerInterceptorAdapterRecipe()
        ));
    }

    /**
     * Remediates Spring @Transactional intra-class self-invocations to avoid proxy bypass.
     */
    public static AstRewriteResult modernizeTransactionSelfInvocation(String sourceCode) {
        if (!sourceCode.contains("Transactional")) {
            return AstRewriteResult.unmodified(sourceCode);
        }

        return rewrite(sourceCode, List.of(
                new SpringTransactionSelfInvocationRecipe()
        ));
    }

    /**
     * Modernizes Spring Cloud Netflix OSS (Eureka, Ribbon, Hystrix, Zuul) to
     * Spring Cloud 2023+ (Spring Cloud Gateway, Resilience4j, Spring Cloud LoadBalancer).
     */
    public static AstRewriteResult modernizeSpringCloud(String sourceCode) {
        if (!sourceCode.contains("Ribbon")
                && !sourceCode.contains("Hystrix")
                && !sourceCode.contains("Zuul")
                && !sourceCode.contains("EnableEurekaClient")
                && !sourceCode.contains("bootstrap.yml")
                && !sourceCode.contains("FeignClient")) {
            return AstRewriteResult.unmodified(sourceCode);
        }

        return rewrite(sourceCode, List.of(
                new SpringCloudRibbonToLoadBalancerRecipe(),
                new SpringCloudHystrixToResilience4jRecipe(),
                new SpringCloudZuulToGatewayRecipe(),
                new SpringCloudEurekaDiscoveryRecipe(),
                new SpringCloudOpenFeignModernizationRecipe(),
                new SpringCloudConfigBootstrapRecipe(),
                new SpringCloudDistributedTracingRecipe()
        ));
    }
}
