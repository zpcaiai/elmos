package io.elmos.worker.cloud;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringAlibabaDubboModernizerTest {
    @TempDir Path root;

    @Test void upgradesAlibabaBomNacosImportAndDubboAnnotations() throws Exception {
        Files.writeString(root.resolve("pom.xml"), """
                <project><dependencyManagement><dependencies><dependency>
                  <groupId>com.alibaba.cloud</groupId><artifactId>spring-cloud-alibaba-dependencies</artifactId>
                  <version>2021.0.5.0</version>
                </dependency></dependencies></dependencyManagement><dependencies><dependency>
                  <groupId>com.alibaba</groupId>
                  <artifactId>dubbo-spring-boot-starter</artifactId><version>2.7.23</version>
                </dependency></dependencies></project>
                """);
        Files.writeString(root.resolve("application.properties"),
                "spring.cloud.nacos.config.server-addr=127.0.0.1:8848\n");
        Path service = root.resolve("OrderService.java");
        Files.writeString(service, """
                import com.alibaba.dubbo.config.annotation.Service;
                import com.alibaba.dubbo.config.annotation.Reference;
                @Service class OrderService { @Reference Object inventory; String note = "@Service"; }
                """);
        var result = SpringAlibabaDubboModernizer.modernize(root);
        assertTrue(result.modified());
        assertTrue(result.blockingObligations().isEmpty());
        String pom = Files.readString(root.resolve("pom.xml"));
        assertTrue(pom.contains("2025.0.0.0"));
        assertTrue(pom.contains("org.apache.dubbo"));
        assertTrue(pom.contains("dubbo-spring-boot-starter3"));
        assertTrue(Files.readString(root.resolve("application.properties")).contains("spring.config.import=optional:nacos:"));
        String java = Files.readString(service);
        assertTrue(java.contains("@DubboService class"));
        assertTrue(java.contains("@DubboReference Object"));
        assertTrue(java.contains("String note = \"@Service\""));
    }

    @Test void addsFlatNacosImportWithoutCreatingDuplicateYamlRoot() throws Exception {
        Path yaml = root.resolve("application.yml");
        Files.writeString(yaml, "spring:\n  application:\n    name: orders\n  cloud:\n    nacos:\n      server-addr: localhost:8848\n");
        SpringAlibabaDubboModernizer.modernize(root);
        String migrated = Files.readString(yaml);
        assertTrue(migrated.contains("spring.config.import: optional:nacos:"));
        assertTrue(migrated.indexOf("spring:\n") == migrated.lastIndexOf("spring:\n"));
    }

    @Test void leavesDubboXmlAsExplicitBlocker() throws Exception {
        Files.writeString(root.resolve("dubbo.xml"), "<beans><dubbo:service interface=\"x.Api\" ref=\"api\"/></beans>");
        var result = SpringAlibabaDubboModernizer.modernize(root);
        assertFalse(result.blockingObligations().isEmpty());
    }
}
