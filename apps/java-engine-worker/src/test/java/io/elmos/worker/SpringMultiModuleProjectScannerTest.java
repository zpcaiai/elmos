package io.elmos.worker;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class SpringMultiModuleProjectScannerTest {

    @TempDir
    Path tempDir;

    @Test
    void findPomFilesReturnsEmptyForNonExistentOrEmptyDirectory() {
        Path nonExistent = tempDir.resolve("non-existent");
        List<Path> poms = SpringMultiModuleProjectScanner.findPomFiles(nonExistent);
        assertTrue(poms.isEmpty());
    }

    @Test
    void findPomFilesFindsRootAndSubmodulePoms() throws IOException {
        Path rootPom = tempDir.resolve("pom.xml");
        Files.writeString(rootPom, """
                <project>
                  <modelVersion>4.0.0</modelVersion>
                  <groupId>com.example</groupId>
                  <artifactId>parent</artifactId>
                  <version>1.0.0</version>
                  <packaging>pom</packaging>
                  <modules>
                    <module>module-a</module>
                    <module>module-b</module>
                  </modules>
                </project>
                """);

        Path moduleADir = tempDir.resolve("module-a");
        Files.createDirectories(moduleADir);
        Files.writeString(moduleADir.resolve("pom.xml"), "<project><artifactId>module-a</artifactId></project>");

        Path moduleBDir = tempDir.resolve("module-b");
        Files.createDirectories(moduleBDir);
        Files.writeString(moduleBDir.resolve("pom.xml"), "<project><artifactId>module-b</artifactId></project>");

        // Also add target and .git dirs which must be skipped
        Path targetDir = tempDir.resolve("target");
        Files.createDirectories(targetDir);
        Files.writeString(targetDir.resolve("pom.xml"), "<project><artifactId>ignored</artifactId></project>");

        Path gitDir = tempDir.resolve(".git");
        Files.createDirectories(gitDir);
        Files.writeString(gitDir.resolve("pom.xml"), "<project><artifactId>ignored</artifactId></project>");

        List<Path> poms = SpringMultiModuleProjectScanner.findPomFiles(tempDir);
        assertEquals(3, poms.size());
        assertTrue(poms.contains(rootPom.toAbsolutePath().normalize()));
        assertTrue(poms.contains(moduleADir.resolve("pom.xml").toAbsolutePath().normalize()));
        assertTrue(poms.contains(moduleBDir.resolve("pom.xml").toAbsolutePath().normalize()));
    }
}
