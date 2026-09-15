package io.elmos.worker.datasource;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringDatasourcePoolAndDriverModernizerTest {

    @TempDir
    Path tempDir;

    @Test
    void modernizesDruidAndOracleDependenciesInPom() throws Exception {
        Path pomFile = tempDir.resolve("pom.xml");
        Files.writeString(pomFile, """
                <project>
                  <dependencies>
                    <dependency>
                      <groupId>com.alibaba</groupId>
                      <artifactId>druid-spring-boot-starter</artifactId>
                      <version>1.1.22</version>
                    </dependency>
                    <dependency>
                      <groupId>com.oracle</groupId>
                      <artifactId>ojdbc6</artifactId>
                      <version>11.2.0.4.0</version>
                    </dependency>
                  </dependencies>
                </project>
                """);

        var result = SpringDatasourcePoolAndDriverModernizer.modernize(tempDir);
        assertTrue(result.modified());
        assertTrue(result.changesCount() >= 2);

        String updatedPom = Files.readString(pomFile);
        assertFalse(updatedPom.contains("druid-spring-boot-starter"));
        assertTrue(updatedPom.contains("druid-spring-boot-3-starter"));
        assertFalse(updatedPom.contains("ojdbc6"));
        assertTrue(updatedPom.contains("ojdbc11"));
    }

    @Test
    void modernizesMysqlDriverClassAndUrlParameters() throws Exception {
        Path appYml = tempDir.resolve("application.yml");
        Files.writeString(appYml, """
                spring:
                  datasource:
                    driver-class-name: com.mysql.jdbc.Driver
                    url: jdbc:mysql://localhost:3306/shop_db?useUnicode=true&characterEncoding=utf-8
                """);

        var result = SpringDatasourcePoolAndDriverModernizer.modernize(tempDir);
        assertTrue(result.modified());

        String updated = Files.readString(appYml);
        assertFalse(updated.contains("com.mysql.jdbc.Driver"));
        assertTrue(updated.contains("com.mysql.cj.jdbc.Driver"));
        assertTrue(updated.contains("serverTimezone=Asia/Shanghai"));
        assertTrue(updated.contains("allowPublicKeyRetrieval=true"));
        assertFalse(updated.contains("useUnicode=true"));
    }
}
