package io.elmos.worker.integration;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Modernizes the deterministic part of legacy SOAP, DWR and JSF surfaces.
 *
 * <p>Remote protocols are never silently changed.  Namespace/API rewrites and the
 * DWR/JSF component model have a safe local subset; Axis, RMI, Hessian, Burlap,
 * HTTP Invoker, Web Flow and Facelets navigation remain explicit runtime/client
 * obligations until both sides of their contracts are executed.
 */
public final class SpringLegacyEnterpriseIntegrationModernizer {
    static final String CXF_VERSION = "4.1.3";

    public record ModernizationResult(
            boolean modified,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            List<String> blockingObligations
    ) {}

    private static final Pattern CXF_PROPERTY = Pattern.compile(
            "(<cxf\\.version>)[^<]+(</cxf\\.version>)");
    private static final Pattern DWR_PROXY = Pattern.compile(
            "@RemoteProxy\\s*(?:\\(\\s*name\\s*=\\s*\"([^\"]+)\"\\s*\\))?");
    private static final Pattern DWR_METHOD = Pattern.compile(
            "@RemoteMethod(?:\\s*\\([^)]*\\))?\\s*(public\\s+(?:[\\w<>, ?\\[\\].]+\\s+)+(\\w+)\\s*\\()",
            Pattern.MULTILINE);
    private static final Pattern JSF_BEAN = Pattern.compile(
            "@ManagedBean(?:\\s*\\(\\s*(?:name\\s*=\\s*)?\"([^\"]+)\"\\s*\\))?");
    private static final Pattern JSF_PROPERTY = Pattern.compile(
            "@ManagedProperty\\s*\\(\\s*value\\s*=\\s*\"#\\{([A-Za-z_$][\\w$]*)}\"\\s*\\)");
    private static final Pattern ANY_JSF_BEAN = Pattern.compile("@ManagedBean(?:\\s*\\([^)]*\\))?");
    private static final Pattern ANY_JSF_PROPERTY = Pattern.compile("@ManagedProperty(?:\\s*\\([^)]*\\))?");

    private SpringLegacyEnterpriseIntegrationModernizer() {}

    public static ModernizationResult modernize(Path projectRoot) {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        Set<String> changed = new LinkedHashSet<>();
        Set<String> rules = new LinkedHashSet<>();
        Set<String> blockers = new LinkedHashSet<>();
        if (!Files.isDirectory(projectRoot)) {
            return new ModernizationResult(false, changed, List.copyOf(rules),
                    List.of("project root does not exist"));
        }

        try (var stream = Files.walk(projectRoot)) {
            for (Path file : stream.filter(Files::isRegularFile).toList()) {
                String relative = relative(projectRoot, file);
                String name = file.getFileName().toString();
                if (name.equals("pom.xml")) {
                    rewritePom(projectRoot, file, changed, rules, blockers);
                } else if (name.endsWith(".java")) {
                    rewriteJava(projectRoot, file, changed, rules, blockers);
                } else if (name.endsWith(".wsdl")) {
                    blockers.add(relative + ": WSDL contract requires generated-client/server diff and source/target SOAP fault replay");
                    rules.add("SOAP_WSDL_CONTRACT_DISCOVERED");
                } else if (name.equals("faces-config.xml") || name.endsWith(".xhtml")) {
                    blockers.add(relative + ": JSF navigation, converter, validator and view-state behavior requires browser/runtime equivalence");
                    rules.add("JSF_VIEW_CONTRACT_DISCOVERED");
                } else if (name.endsWith("-flow.xml")) {
                    blockers.add(relative + ": Spring Web Flow state transitions require an explicit state-machine mapping and replay");
                    rules.add("SPRING_WEB_FLOW_CONTRACT_DISCOVERED");
                } else if (name.equals("dwr.xml")) {
                    blockers.add(relative + ": XML-declared DWR remotes require method allowlist, authz and serialization reconciliation");
                    rules.add("DWR_XML_CONTRACT_DISCOVERED");
                }
            }
        } catch (IOException error) {
            blockers.add("IO:" + error.getClass().getSimpleName());
        }
        return new ModernizationResult(!changed.isEmpty(), Set.copyOf(changed),
                List.copyOf(rules), List.copyOf(blockers));
    }

    private static void rewritePom(Path root, Path pom, Set<String> changed,
                                   Set<String> rules, Set<String> blockers) throws IOException {
        String before = Files.readString(pom, StandardCharsets.UTF_8);
        String after = before
                .replace("<groupId>javax.xml.ws</groupId>", "<groupId>jakarta.xml.ws</groupId>")
                .replace("<artifactId>jaxws-api</artifactId>", "<artifactId>jakarta.xml.ws-api</artifactId>")
                .replace("<groupId>javax.jws</groupId>", "<groupId>jakarta.jws</groupId>")
                .replace("<artifactId>javax.jws-api</artifactId>", "<artifactId>jakarta.jws-api</artifactId>");
        after = CXF_PROPERTY.matcher(after).replaceAll("$1" + CXF_VERSION + "$2");
        if (!after.equals(before)) {
            Files.writeString(pom, after, StandardCharsets.UTF_8);
            changed.add(relative(root, pom));
            rules.add("JAX_WS_JAKARTA_NAMESPACE_AND_CXF_4_1");
        }
        if (before.contains("org.apache.axis") || before.contains("axis2")) {
            blockers.add(relative(root, pom) + ": Axis RPC/encoding and handler chains require WSDL-first CXF or Spring-WS contract migration");
        }
        if (containsAny(before, "spring-remoting", "hessian", "burlap", "httpinvoker", "spring-rmi")) {
            blockers.add(relative(root, pom) + ": legacy binary/Java-serialization RPC requires a versioned compatibility bridge and client cutover");
        }
    }

    private static void rewriteJava(Path root, Path file, Set<String> changed,
                                    Set<String> rules, Set<String> blockers) throws IOException {
        String before = Files.readString(file, StandardCharsets.UTF_8);
        List<String> fileRules = new ArrayList<>();
        List<String> fileBlockers = new ArrayList<>();
        String after = modernizeJavaSource(before, fileRules, fileBlockers);
        if (containsAny(after, "RmiServiceExporter", "RmiProxyFactoryBean", "HttpInvokerServiceExporter",
                "HttpInvokerProxyFactoryBean", "HessianServiceExporter", "BurlapServiceExporter")) {
            fileBlockers.add(relative(root, file) + ": remote interface, serialization filter, retry and client compatibility evidence is required");
        }
        if (!after.equals(before)) {
            Files.writeString(file, after, StandardCharsets.UTF_8);
            changed.add(relative(root, file));
            rules.addAll(fileRules);
        }
        for (String b : fileBlockers) {
            blockers.add(b.contains(":") ? b : relative(root, file) + ": " + b);
        }
    }

    /**
     * Modernizes in-memory Java source code for legacy SOAP (JAX-WS to Jakarta XML WS),
     * DWR (@RemoteProxy to @RestController), and JSF (@ManagedBean to @Component).
     */
    public static String modernizeJavaSource(String source, List<String> rules, List<String> blockers) {
        if (source == null || source.isBlank()) return source;
        String after = source
                .replace("import javax.jws.", "import jakarta.jws.")
                .replace("import javax.xml.ws.", "import jakarta.xml.ws.");
        if (!after.equals(source) && rules != null) rules.add("JAX_WS_JAKARTA_SOURCE_NAMESPACE");

        if (after.contains("org.directwebremoting.annotations.RemoteProxy")) {
            after = after.replace("import org.directwebremoting.annotations.RemoteProxy;",
                    "import org.springframework.web.bind.annotation.RestController;\n"
                            + "import org.springframework.web.bind.annotation.RequestMapping;");
            after = after.replace("import org.directwebremoting.annotations.RemoteMethod;",
                    "import org.springframework.web.bind.annotation.PostMapping;");
            Matcher proxy = DWR_PROXY.matcher(after);
            if (proxy.find()) {
                String proxyName = proxy.group(1) == null ? "remote" : proxy.group(1);
                after = proxy.replaceFirst(Matcher.quoteReplacement(
                        "@RestController\n@RequestMapping(\"/dwr/" + proxyName + "\")"));
            }
            Matcher methods = DWR_METHOD.matcher(after);
            StringBuffer rewritten = new StringBuffer();
            while (methods.find()) {
                methods.appendReplacement(rewritten, Matcher.quoteReplacement(
                        "@PostMapping(\"/" + methods.group(2) + "\")\n    " + methods.group(1)));
            }
            methods.appendTail(rewritten);
            after = rewritten.toString();
            if (rules != null) rules.add("DWR_ANNOTATED_REMOTE_TO_REST_CONTROLLER");
            if (blockers != null) blockers.add("DWR-to-REST requires authz, batching, exception and JSON serialization differential tests");
        }

        if (after.contains("javax.faces.bean.ManagedBean")) {
            if (!allMatches(after, ANY_JSF_BEAN, JSF_BEAN)
                    || !allMatches(after, ANY_JSF_PROPERTY, JSF_PROPERTY)) {
                if (blockers != null) blockers.add("JSF managed-bean or managed-property expression is outside the deterministic Spring component subset");
                return after;
            }
            after = after.replace("import javax.faces.bean.ManagedBean;",
                    "import org.springframework.stereotype.Component;")
                    .replace("import javax.faces.bean.ManagedProperty;",
                            "import org.springframework.beans.factory.annotation.Autowired;\n"
                                    + "import org.springframework.beans.factory.annotation.Qualifier;");
            Matcher bean = JSF_BEAN.matcher(after);
            StringBuffer beans = new StringBuffer();
            while (bean.find()) {
                String replacement = bean.group(1) == null ? "@Component" : "@Component(\"" + bean.group(1) + "\")";
                bean.appendReplacement(beans, Matcher.quoteReplacement(replacement));
            }
            bean.appendTail(beans);
            Matcher properties = JSF_PROPERTY.matcher(beans.toString());
            StringBuffer qualified = new StringBuffer();
            while (properties.find()) {
                properties.appendReplacement(qualified, Matcher.quoteReplacement(
                        "@Autowired\n    @Qualifier(\"" + properties.group(1) + "\")"));
            }
            properties.appendTail(qualified);
            after = qualified.toString();
            if (rules != null) rules.add("JSF_MANAGED_BEAN_TO_SPRING_COMPONENT");
            if (blockers != null) blockers.add("JSF scopes, view state, EL method bindings and navigation require runtime reconciliation");
        }
        return after;
    }

    private static boolean containsAny(String text, String... values) {
        for (String value : values) if (text.contains(value)) return true;
        return false;
    }

    private static boolean allMatches(String source, Pattern broad, Pattern supported) {
        Matcher candidates = broad.matcher(source);
        while (candidates.find()) {
            if (!supported.matcher(candidates.group()).matches()) return false;
        }
        return true;
    }

    private static String fileNameStem(Path file) {
        String name = file.getFileName().toString();
        int dot = name.lastIndexOf('.');
        return dot < 0 ? name : name.substring(0, dot);
    }

    private static String relative(Path root, Path file) {
        return root.relativize(file).toString().replace('\\', '/');
    }
}
