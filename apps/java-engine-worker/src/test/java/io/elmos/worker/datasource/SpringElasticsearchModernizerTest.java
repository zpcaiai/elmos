package io.elmos.worker.datasource;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringElasticsearchModernizerTest {

    @TempDir
    Path tempDir;

    @Test
    void modernizesElasticsearchStarterDependencyInPom() throws Exception {
        Path pomFile = tempDir.resolve("pom.xml");
        Files.writeString(pomFile, """
                <project>
                  <dependencies>
                    <dependency>
                      <groupId>org.elasticsearch.client</groupId>
                      <artifactId>elasticsearch-rest-high-level-client</artifactId>
                      <version>7.17.6</version>
                    </dependency>
                  </dependencies>
                </project>
                """);

        var result = SpringElasticsearchModernizer.modernize(tempDir);
        assertTrue(result.modified());
        assertTrue(result.changesCount() >= 1);

        String updated = Files.readString(pomFile);
        assertFalse(updated.contains("elasticsearch-rest-high-level-client"));
        assertTrue(updated.contains("spring-boot-starter-data-elasticsearch"));

        Path generatedConfig = tempDir.resolve("src/main/java/io/elmos/generated/es/ElasticsearchClientConfiguration.java");
        assertTrue(Files.isRegularFile(generatedConfig));
    }

    @Test
    void modernizesJavaImportsAndTypeUsages() throws Exception {
        Path javaFile = tempDir.resolve("src/main/java/com/example/ProductSearchService.java");
        Files.createDirectories(javaFile.getParent());
        Files.writeString(javaFile, """
                package com.example;

                import org.elasticsearch.client.RestHighLevelClient;
                import org.springframework.data.elasticsearch.core.ElasticsearchRestTemplate;

                public class ProductSearchService {
                    private RestHighLevelClient client;
                    private ElasticsearchRestTemplate template;
                }
                """);

        var result = SpringElasticsearchModernizer.modernize(tempDir);
        assertTrue(result.modified());

        String updated = Files.readString(javaFile);
        assertFalse(updated.contains("RestHighLevelClient"));
        assertFalse(updated.contains("ElasticsearchRestTemplate"));
        assertTrue(updated.contains("co.elastic.clients.elasticsearch.ElasticsearchClient"));
        assertTrue(updated.contains("ElasticsearchOperations"));
    }
}
