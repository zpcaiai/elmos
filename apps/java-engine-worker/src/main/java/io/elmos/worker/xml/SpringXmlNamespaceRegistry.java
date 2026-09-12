package io.elmos.worker.xml;

import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;

import java.util.*;

/**
 * Registry and dispatch engine for Spring XML custom namespaces:
 * context:, tx:, mvc:, aop:, and security:.
 */
public final class SpringXmlNamespaceRegistry {

    public interface NamespaceHandler {
        void handleElement(Element element, NamespaceParsingContext context);
    }

    public static final class NamespaceParsingContext {
        private final Set<String> classAnnotations = new LinkedHashSet<>();
        private final Set<String> requiredImports = new LinkedHashSet<>();
        private final List<String> helperMethods = new ArrayList<>();
        private final List<String> propertySources = new ArrayList<>();
        private final List<String> componentScans = new ArrayList<>();

        public void addAnnotation(String annotation) {
            classAnnotations.add(annotation);
        }

        public void addImport(String fqcn) {
            requiredImports.add(fqcn);
        }

        public void addHelperMethod(String methodCode) {
            helperMethods.add(methodCode);
        }

        public void addPropertySource(String location) {
            propertySources.add(location);
        }

        public void addComponentScan(String pkg) {
            componentScans.add(pkg);
        }

        public Set<String> getClassAnnotations() { return Collections.unmodifiableSet(classAnnotations); }
        public Set<String> getRequiredImports() { return Collections.unmodifiableSet(requiredImports); }
        public List<String> getHelperMethods() { return Collections.unmodifiableList(helperMethods); }
        public List<String> getPropertySources() { return Collections.unmodifiableList(propertySources); }
        public List<String> getComponentScans() { return Collections.unmodifiableList(componentScans); }
    }

    private final Map<String, NamespaceHandler> handlers = new HashMap<>();

    public SpringXmlNamespaceRegistry() {
        registerDefaultHandlers();
    }

    private void registerDefaultHandlers() {
        // 1. Context namespace
        handlers.put("context:component-scan", (element, ctx) -> {
            String basePkg = element.getAttribute("base-package");
            if (!basePkg.isBlank()) {
                ctx.addComponentScan(basePkg);
                ctx.addImport("org.springframework.context.annotation.ComponentScan");
                ctx.addAnnotation("@ComponentScan(basePackages = \"" + basePkg + "\")");
            }
        });

        handlers.put("context:property-placeholder", (element, ctx) -> {
            String location = element.getAttribute("location");
            if (!location.isBlank()) {
                ctx.addPropertySource(location);
                ctx.addImport("org.springframework.context.annotation.PropertySource");
                ctx.addAnnotation("@PropertySource(\"" + location + "\")");
            }
        });

        handlers.put("context:annotation-config", (element, ctx) -> {
            // Implicit in Spring Boot / @Configuration
            ctx.addImport("org.springframework.context.annotation.Configuration");
        });

        // 2. Tx namespace
        handlers.put("tx:annotation-driven", (element, ctx) -> {
            ctx.addImport("org.springframework.transaction.annotation.EnableTransactionManagement");
            String txManager = element.getAttribute("transaction-manager");
            if (!txManager.isBlank() && !"transactionManager".equals(txManager)) {
                ctx.addAnnotation("@EnableTransactionManagement");
            } else {
                ctx.addAnnotation("@EnableTransactionManagement");
            }
        });

        // 3. MVC namespace
        handlers.put("mvc:annotation-driven", (element, ctx) -> {
            ctx.addImport("org.springframework.web.servlet.config.annotation.EnableWebMvc");
            ctx.addImport("org.springframework.web.servlet.config.annotation.WebMvcConfigurer");
            ctx.addAnnotation("@EnableWebMvc");
        });

        handlers.put("mvc:default-servlet-handler", (element, ctx) -> {
            ctx.addImport("org.springframework.web.servlet.config.annotation.DefaultServletHandlerConfigurer");
            ctx.addHelperMethod("""
                    @Override
                    public void configureDefaultServletHandling(DefaultServletHandlerConfigurer configurer) {
                        configurer.enable();
                    }
                    """);
        });

        // 4. AOP namespace
        handlers.put("aop:aspectj-autoproxy", (element, ctx) -> {
            ctx.addImport("org.springframework.context.annotation.EnableAspectJAutoProxy");
            String proxyTargetClass = element.getAttribute("proxy-target-class");
            if ("true".equalsIgnoreCase(proxyTargetClass)) {
                ctx.addAnnotation("@EnableAspectJAutoProxy(proxyTargetClass = true)");
            } else {
                ctx.addAnnotation("@EnableAspectJAutoProxy");
            }
        });

        // 5. Security namespace
        handlers.put("security:http", (element, ctx) -> {
            ctx.addImport("org.springframework.security.config.annotation.web.configuration.EnableWebSecurity");
            ctx.addImport("org.springframework.security.web.SecurityFilterChain");
            ctx.addImport("org.springframework.security.config.annotation.web.builders.HttpSecurity");
            ctx.addImport("org.springframework.context.annotation.Bean");
            ctx.addAnnotation("@EnableWebSecurity");
        });
    }

    public void processElement(Element element, NamespaceParsingContext context) {
        String tagName = element.getTagName();
        NamespaceHandler handler = handlers.get(tagName);
        if (handler != null) {
            handler.handleElement(element, context);
        }
    }

    public boolean isCustomNamespace(String tagName) {
        return tagName.contains(":") && !tagName.startsWith("beans:");
    }
}
