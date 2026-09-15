package io.elmos.recipes.transaction;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.Expression;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.Statement;
import org.openrewrite.java.tree.TypeTree;

import java.util.*;

/**
 * OpenRewrite recipe to automatically detect and remediate Spring @Transactional proxy-bypass self-invocations.
 *
 * <p>When a method inside a Spring bean calls another method annotated with {@code @Transactional} on {@code this},
 * the call bypasses the Spring AOP proxy, silently ignoring transaction boundaries and rollback rules.
 *
 * <p>Remediation strategy:
 * <ol>
 *   <li>Identifies intra-class call sites targeting {@code @Transactional} methods.</li>
 *   <li>Rewrites {@code this.txMethod(...)} or {@code txMethod(...)} to {@code self.txMethod(...)}.</li>
 *   <li>Injects {@code @Lazy @Autowired private CurrentClass self;} self-reference bean proxy into the class.</li>
 *   <li>Adds necessary imports for {@code @Lazy} and {@code @Autowired}.</li>
 * </ol>
 */
public final class SpringTransactionSelfInvocationRecipe extends Recipe {

    @Override
    public String getDisplayName() {
        return "Remediate @Transactional Proxy Self-Invocations";
    }

    @Override
    public String getDescription() {
        return "Injects @Lazy self-reference and redirects intra-class @Transactional invocations to avoid AOP proxy bypass.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {
            @Override
            public J.ClassDeclaration visitClassDeclaration(J.ClassDeclaration classDecl, ExecutionContext ctx) {
                J.ClassDeclaration cd = super.visitClassDeclaration(classDecl, ctx);
                String className = cd.getSimpleName();
                if (cd.getBody() == null) {
                    return cd;
                }

                // 1. Find all @Transactional methods in this class
                Set<String> txMethods = new HashSet<>();
                boolean hasSelfField = false;

                for (Statement stmt : cd.getBody().getStatements()) {
                    if (stmt instanceof J.MethodDeclaration md) {
                        for (J.Annotation a : md.getLeadingAnnotations()) {
                            if ("Transactional".equals(a.getSimpleName())) {
                                txMethods.add(md.getSimpleName());
                                break;
                            }
                        }
                    } else if (stmt instanceof J.VariableDeclarations vd) {
                        for (J.VariableDeclarations.NamedVariable v : vd.getVariables()) {
                            if ("self".equals(v.getSimpleName())) {
                                hasSelfField = true;
                                break;
                            }
                        }
                    }
                }

                if (txMethods.isEmpty()) {
                    return cd;
                }

                // 2. Visit methods and rewrite self-invocations
                boolean[] modified = new boolean[]{false};
                List<Statement> updatedStatements = new ArrayList<>();

                for (Statement stmt : cd.getBody().getStatements()) {
                    if (stmt instanceof J.MethodDeclaration md && md.getBody() != null) {
                        String callerName = md.getSimpleName();
                        J.MethodDeclaration updatedMd = (J.MethodDeclaration) md.acceptJava(new JavaIsoVisitor<ExecutionContext>() {
                            @Override
                            public J.MethodInvocation visitMethodInvocation(J.MethodInvocation method, ExecutionContext c) {
                                J.MethodInvocation mi = super.visitMethodInvocation(method, c);
                                String name = mi.getSimpleName();
                                if (txMethods.contains(name) && !name.equals(callerName)) {
                                    Expression select = mi.getSelect();
                                    boolean isSelfCall = false;
                                    if (select == null) {
                                        isSelfCall = true;
                                    } else if (select instanceof J.Identifier id && "this".equals(id.getSimpleName())) {
                                        isSelfCall = true;
                                    }

                                    if (isSelfCall) {
                                        modified[0] = true;
                                        return mi.withSelect(TypeTree.build("self"));
                                    }
                                }
                                return mi;
                            }
                        }, ctx);
                        updatedStatements.add(updatedMd);
                    } else {
                        updatedStatements.add(stmt);
                    }
                }

                // 3. If any self-invocations were rewritten, inject @Lazy @Autowired private CurrentClass self;
                if (modified[0] && !hasSelfField) {
                    maybeAddImport("org.springframework.context.annotation.Lazy");
                    maybeAddImport("org.springframework.beans.factory.annotation.Autowired");

                    String fieldCode = "class _T_ {\n    @org.springframework.context.annotation.Lazy\n    @org.springframework.beans.factory.annotation.Autowired\n    private " + className + " self;\n}";
                    try {
                        org.openrewrite.SourceFile parsed = org.openrewrite.java.JavaParser.fromJavaVersion().build().parse(fieldCode).findFirst().orElse(null);
                        if (parsed instanceof J.CompilationUnit cu && !cu.getClasses().isEmpty()) {
                            Statement fieldStmt = cu.getClasses().get(0).getBody().getStatements().get(0);
                            List<Statement> withField = new ArrayList<>();
                            withField.add(fieldStmt);
                            withField.addAll(updatedStatements);
                            cd = cd.withBody(cd.getBody().withStatements(withField));
                        } else {
                            cd = cd.withBody(cd.getBody().withStatements(updatedStatements));
                        }
                    } catch (Exception e) {
                        cd = cd.withBody(cd.getBody().withStatements(updatedStatements));
                    }
                } else if (modified[0]) {
                    cd = cd.withBody(cd.getBody().withStatements(updatedStatements));
                }

                return cd;
            }
        };
    }
}
