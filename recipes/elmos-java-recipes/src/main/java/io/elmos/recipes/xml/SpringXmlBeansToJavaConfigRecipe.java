package io.elmos.recipes.xml;

import org.openrewrite.ExecutionContext;
import org.openrewrite.Recipe;
import org.openrewrite.TreeVisitor;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.TypeTree;

/**
 * OpenRewrite recipe to modernize legacy XML-bearing Spring configurations.
 *
 * <p>Key transformations:
 * <ol>
 *   <li>Detects and modernizes {@code @ImportResource} declarations.</li>
 *   <li>Replaces {@code ClassPathXmlApplicationContext} or {@code FileSystemXmlApplicationContext} usages with {@code AnnotationConfigApplicationContext}.</li>
 *   <li>Adds modern Spring {@code @Configuration} annotations to designated migration classes.</li>
 * </ol>
 */
public final class SpringXmlBeansToJavaConfigRecipe extends Recipe {

    @Override
    public String getDisplayName() {
        return "Modernize Spring XML ImportResource to JavaConfig";
    }

    @Override
    public String getDescription() {
        return "Transitions XML-configured Spring applications toward pure annotation-based JavaConfig.";
    }

    @Override
    public TreeVisitor<?, ExecutionContext> getVisitor() {
        return new JavaIsoVisitor<ExecutionContext>() {

            @Override
            public J.Annotation visitAnnotation(J.Annotation annotation, ExecutionContext ctx) {
                J.Annotation a = super.visitAnnotation(annotation, ctx);
                if ("ImportResource".equals(a.getSimpleName())) {
                    maybeRemoveImport("org.springframework.context.annotation.ImportResource");
                    maybeAddImport("org.springframework.context.annotation.Configuration");
                    maybeAddImport("org.springframework.context.annotation.Import");
                    // Transform to @Configuration if not already present
                    a = a.withAnnotationType(TypeTree.build("Configuration").withPrefix(a.getAnnotationType().getPrefix()));
                }
                return a;
            }

            @Override
            public J.VariableDeclarations visitVariableDeclarations(J.VariableDeclarations multiVariable, ExecutionContext ctx) {
                J.VariableDeclarations mv = super.visitVariableDeclarations(multiVariable, ctx);
                if (mv.getTypeExpression() != null) {
                    String typeName = mv.getTypeExpression().printTrimmed();
                    if ("ClassPathXmlApplicationContext".equals(typeName) || "FileSystemXmlApplicationContext".equals(typeName)) {
                        maybeRemoveImport("org.springframework.context.support.ClassPathXmlApplicationContext");
                        maybeRemoveImport("org.springframework.context.support.FileSystemXmlApplicationContext");
                        maybeAddImport("org.springframework.context.annotation.AnnotationConfigApplicationContext");
                        mv = mv.withTypeExpression(TypeTree.build("AnnotationConfigApplicationContext")
                                .withPrefix(mv.getTypeExpression().getPrefix()));
                    }
                }
                return mv;
            }

            @Override
            public J.MethodDeclaration visitMethodDeclaration(J.MethodDeclaration method, ExecutionContext ctx) {
                J.MethodDeclaration m = super.visitMethodDeclaration(method, ctx);
                if (m.getReturnTypeExpression() != null) {
                    String retName = m.getReturnTypeExpression().printTrimmed();
                    if ("ClassPathXmlApplicationContext".equals(retName) || "FileSystemXmlApplicationContext".equals(retName)) {
                        maybeRemoveImport("org.springframework.context.support.ClassPathXmlApplicationContext");
                        maybeRemoveImport("org.springframework.context.support.FileSystemXmlApplicationContext");
                        maybeAddImport("org.springframework.context.annotation.AnnotationConfigApplicationContext");
                        m = m.withReturnTypeExpression(TypeTree.build("AnnotationConfigApplicationContext")
                                .withPrefix(m.getReturnTypeExpression().getPrefix()));
                    }
                }
                return m;
            }

            @Override
            public J.NewClass visitNewClass(J.NewClass newClass, ExecutionContext ctx) {
                J.NewClass nc = super.visitNewClass(newClass, ctx);
                if (nc.getClazz() != null) {
                    String className = nc.getClazz().printTrimmed();
                    if (className.contains("ClassPathXmlApplicationContext") || className.contains("FileSystemXmlApplicationContext")) {
                        maybeRemoveImport("org.springframework.context.support.ClassPathXmlApplicationContext");
                        maybeRemoveImport("org.springframework.context.support.FileSystemXmlApplicationContext");
                        maybeAddImport("org.springframework.context.annotation.AnnotationConfigApplicationContext");
                        nc = nc.withClazz(TypeTree.build("AnnotationConfigApplicationContext").withPrefix(nc.getClazz().getPrefix()));
                    }
                }
                return nc;
            }
        };
    }
}
