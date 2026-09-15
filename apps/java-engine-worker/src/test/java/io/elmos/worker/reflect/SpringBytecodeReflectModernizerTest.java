package io.elmos.worker.reflect;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class SpringBytecodeReflectModernizerTest {

    @TempDir
    Path tempDir;

    @Test
    void testCglibToSpringCglibAndMakeAccessible() throws IOException {
        Path javaDir = Files.createDirectories(tempDir.resolve("src/main/java/com/example"));
        Path javaFile = javaDir.resolve("ProxyUtil.java");
        Files.writeString(javaFile, """
                package com.example;
                
                import net.sf.cglib.proxy.Enhancer;
                import net.sf.cglib.proxy.MethodInterceptor;
                import java.lang.reflect.Field;
                
                public class ProxyUtil {
                    public static void modifyField(Object target, String name, Object val) throws Exception {
                        Field field = target.getClass().getDeclaredField(name);
                        field.setAccessible(true);
                        field.set(target, val);
                    }
                }
                """);

        var result = SpringBytecodeReflectModernizer.modernize(tempDir);

        assertTrue(result.modified());
        assertTrue(result.rulesApplied().contains("JAVA_CGLIB_TO_SPRING_CGLIB"));
        assertTrue(result.rulesApplied().contains("JAVA_REFLECTIONUTILS_MAKE_ACCESSIBLE"));

        String content = Files.readString(javaFile);
        assertTrue(content.contains("import org.springframework.cglib.proxy.Enhancer;"));
        assertTrue(content.contains("import org.springframework.cglib.proxy.MethodInterceptor;"));
        assertTrue(content.contains("ReflectionUtils.makeAccessible(field);"));
        assertTrue(content.contains("import org.springframework.util.ReflectionUtils;"));

        // Check generated jvm.argfile
        Path argFile = tempDir.resolve("src/main/resources/META-INF/jvm.argfile");
        assertTrue(Files.exists(argFile), "jvm.argfile must be generated for JDK internal reflection");
        String argContent = Files.readString(argFile);
        assertTrue(argContent.contains("--add-opens java.base/java.lang=ALL-UNNAMED"));
    }

    @Test
    void testPomRemovesCglibAndInjectsSurefireArgLine() throws IOException {
        Path pom = tempDir.resolve("pom.xml");
        Files.writeString(pom, """
                <project>
                    <dependencies>
                        <dependency>
                            <groupId>cglib</groupId>
                            <artifactId>cglib</artifactId>
                            <version>3.3.0</version>
                        </dependency>
                    </dependencies>
                    <build>
                        <plugins>
                            <plugin>
                                <artifactId>maven-surefire-plugin</artifactId>
                                <configuration>
                                    <argLine>-Xmx512m</argLine>
                                </configuration>
                            </plugin>
                        </plugins>
                    </build>
                </project>
                """);

        Path javaDir = Files.createDirectories(tempDir.resolve("src/main/java/com/example"));
        Path javaFile = javaDir.resolve("InternalAccessor.java");
        Files.writeString(javaFile, """
                package com.example;
                import java.lang.reflect.Field;
                public class InternalAccessor {
                    void test(Field f) { f.setAccessible(true); }
                }
                """);

        var result = SpringBytecodeReflectModernizer.modernize(tempDir);

        assertTrue(result.modified());
        assertTrue(result.rulesApplied().contains("POM_REMOVE_CGLIB_DEPENDENCY"));
        assertTrue(result.rulesApplied().contains("POM_SUREFIRE_ADD_OPENS_INJECTED"));

        String updatedPom = Files.readString(pom);
        assertFalse(updatedPom.contains("<artifactId>cglib</artifactId>"));
        assertTrue(updatedPom.contains("--add-opens java.base/java.lang=ALL-UNNAMED"));
    }
}
