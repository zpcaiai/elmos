package io.elmos.worker.integration;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringLegacyEnterpriseIntegrationModernizerTest {
    @TempDir Path root;

    @Test void modernizesJaxWsDwrAndJsfSupportedSubsets() throws Exception {
        Files.writeString(root.resolve("pom.xml"), """
                <project><properties><cxf.version>3.5.8</cxf.version></properties><dependencies>
                  <dependency><groupId>javax.xml.ws</groupId><artifactId>jaxws-api</artifactId></dependency>
                  <dependency><groupId>javax.jws</groupId><artifactId>javax.jws-api</artifactId></dependency>
                </dependencies></project>
                """);
        Path dwr = root.resolve("OrderRemote.java");
        Files.writeString(dwr, """
                import org.directwebremoting.annotations.RemoteProxy;
                import org.directwebremoting.annotations.RemoteMethod;
                @RemoteProxy(name = "orders")
                public class OrderRemote {
                    @RemoteMethod
                    public String load(String id) { return id; }
                }
                """);
        Path bean = root.resolve("OrderBean.java");
        Files.writeString(bean, """
                import javax.faces.bean.ManagedBean;
                import javax.faces.bean.ManagedProperty;
                @ManagedBean(name = "order")
                public class OrderBean { @ManagedProperty(value = "#{service}") Object service; }
                """);
        Path endpoint = root.resolve("OrderEndpoint.java");
        Files.writeString(endpoint, "import javax.jws.WebService; import javax.xml.ws.BindingType;");

        var result = SpringLegacyEnterpriseIntegrationModernizer.modernize(root);

        assertTrue(result.modified());
        assertTrue(Files.readString(root.resolve("pom.xml")).contains("<cxf.version>4.1.3</cxf.version>"));
        String dwrSource = Files.readString(dwr);
        assertTrue(dwrSource.contains("@RestController"));
        assertTrue(dwrSource.contains("@RequestMapping(\"/dwr/orders\")"));
        assertTrue(dwrSource.contains("@PostMapping(\"/load\")"));
        String beanSource = Files.readString(bean);
        assertTrue(beanSource.contains("@Component(\"order\")"));
        assertTrue(beanSource.contains("@Autowired"));
        assertTrue(beanSource.contains("@Qualifier(\"service\")"));
        assertTrue(Files.readString(endpoint).contains("import jakarta.jws.WebService"));
        assertFalse(result.blockingObligations().isEmpty(), "runtime protocol/view obligations must remain explicit");
    }

    @Test void inventoriesUnsafeRemoteAndViewContractsWithoutGuessing() throws Exception {
        Files.writeString(root.resolve("pom.xml"), """
                <project><dependencies><dependency><groupId>org.apache.axis</groupId>
                  <artifactId>axis</artifactId></dependency></dependencies></project>
                """);
        Files.writeString(root.resolve("legacy.wsdl"), "<definitions/>");
        Files.writeString(root.resolve("checkout-flow.xml"), "<flow/>");
        Files.writeString(root.resolve("view.xhtml"), "<html/>");
        Files.writeString(root.resolve("RemoteConfig.java"), "class RemoteConfig { RmiServiceExporter exporter; }");

        var result = SpringLegacyEnterpriseIntegrationModernizer.modernize(root);

        assertFalse(result.blockingObligations().isEmpty());
        assertTrue(result.blockingObligations().stream().anyMatch(value -> value.contains("Axis")));
        assertTrue(result.blockingObligations().stream().anyMatch(value -> value.contains("WSDL")));
        assertTrue(result.blockingObligations().stream().anyMatch(value -> value.contains("Web Flow")));
        assertTrue(result.blockingObligations().stream().anyMatch(value -> value.contains("JSF")));
        assertTrue(result.blockingObligations().stream().anyMatch(value -> value.contains("remote interface")));
    }

    @Test void retainsUnsupportedJsfExpressionsAtomically() throws Exception {
        Path bean = root.resolve("OrderBean.java");
        String original = """
                import javax.faces.bean.ManagedBean;
                import javax.faces.bean.ManagedProperty;
                @ManagedBean(name = "order", eager = true)
                public class OrderBean { @ManagedProperty(value = "#{service.delegate}") Object service; }
                """;
        Files.writeString(bean, original);

        var result = SpringLegacyEnterpriseIntegrationModernizer.modernize(root);

        assertTrue(result.blockingObligations().stream().anyMatch(value -> value.contains("outside the deterministic")));
        assertTrue(Files.readString(bean).equals(original));
    }
}
