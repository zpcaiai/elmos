package io.elmos.worker.messaging;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringActiveMqToArtemisModernizerTest {
    @TempDir Path root;

    @Test void migratesStarterJakartaNamespaceAndProperties() throws Exception {
        Files.writeString(root.resolve("pom.xml"), """
                <project><dependencies><dependency><groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-starter-activemq</artifactId></dependency>
                <dependency><groupId>org.apache.activemq</groupId><artifactId>activemq-client</artifactId></dependency>
                </dependencies></project>
                """);
        Path listener = root.resolve("Listener.java");
        Files.writeString(listener, """
                import javax.jms.Message;
                import org.apache.activemq.ActiveMQConnectionFactory;
                class Listener { Message accept(Message value) { return value; } }
                """);
        Files.writeString(root.resolve("application.properties"), "spring.activemq.broker-url=tcp://localhost:61616\n");
        var result = SpringActiveMqToArtemisModernizer.modernize(root);
        assertTrue(result.modified());
        assertTrue(result.blockingObligations().isEmpty());
        String pom = Files.readString(root.resolve("pom.xml"));
        assertTrue(pom.contains("spring-boot-starter-artemis"));
        assertTrue(pom.indexOf("spring-boot-starter-artemis") == pom.lastIndexOf("spring-boot-starter-artemis"));
        assertTrue(Files.readString(listener).contains("jakarta.jms.Message"));
        assertTrue(Files.readString(listener).contains("artemis.jms.client.ActiveMQConnectionFactory"));
        assertTrue(Files.readString(root.resolve("application.properties")).contains("spring.artemis.broker-url"));
    }

    @Test void blocksClassicSpecificPolicies() throws Exception {
        Path source = root.resolve("Policy.java");
        String before = "import javax.jms.Message; class Policy { ActiveMQPrefetchPolicy policy; }";
        Files.writeString(source, before);
        var result = SpringActiveMqToArtemisModernizer.modernize(root);
        assertFalse(result.blockingObligations().isEmpty());
        assertTrue(Files.readString(source).equals(before));
    }
}
