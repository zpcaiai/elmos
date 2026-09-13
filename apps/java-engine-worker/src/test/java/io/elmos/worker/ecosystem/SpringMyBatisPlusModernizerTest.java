package io.elmos.worker.ecosystem;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringMyBatisPlusModernizerTest {
    @TempDir Path root;

    @Test void upgradesStarterAndExplicitPaginationPlugin() throws Exception {
        Files.writeString(root.resolve("pom.xml"), """
                <project><dependencies><dependency>
                  <groupId>com.baomidou</groupId>
                  <artifactId>mybatis-plus-boot-starter</artifactId>
                  <version>3.4.3</version>
                </dependency></dependencies></project>
                """);
        Path config = root.resolve("MybatisConfig.java");
        Files.writeString(config, """
                import com.baomidou.mybatisplus.annotation.DbType;
                import com.baomidou.mybatisplus.extension.plugins.PaginationInterceptor;
                class MybatisConfig {
                    PaginationInterceptor paginationInterceptor() {
                        DbType type = DbType.MYSQL;
                        return new PaginationInterceptor();
                    }
                }
                """);

        var result = SpringMyBatisPlusModernizer.modernize(root);

        assertTrue(result.modified());
        assertTrue(result.blockingObligations().isEmpty());
        String pom = Files.readString(root.resolve("pom.xml"));
        assertTrue(pom.contains("mybatis-plus-spring-boot3-starter"));
        assertTrue(pom.contains("<version>3.5.17</version>"));
        String java = Files.readString(config);
        assertTrue(java.contains("MybatisPlusInterceptor mybatisPlusInterceptor()"));
        assertTrue(java.contains("new PaginationInnerInterceptor(DbType.MYSQL)"));
    }

    @Test void refusesToGuessPaginationDatabaseTypeAndIsIdempotent() throws Exception {
        Files.writeString(root.resolve("pom.xml"), "<project/>");
        Path config = root.resolve("MybatisConfig.java");
        String source = "class MybatisConfig { PaginationInterceptor paginationInterceptor() { return new PaginationInterceptor(); } }";
        Files.writeString(config, source);
        var first = SpringMyBatisPlusModernizer.modernize(root);
        assertFalse(first.blockingObligations().isEmpty());
        assertEquals(source, Files.readString(config));
        var second = SpringMyBatisPlusModernizer.modernize(root);
        assertFalse(second.modified());
    }
}
