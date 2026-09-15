package io.elmos.worker.schedule;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringScheduleAndLockModernizerTest {

    @TempDir
    Path tempDir;

    @Test
    void modernizesBareScheduledTasksWithShedLockAndUpgradesXxlJob() throws Exception {
        Path pomFile = tempDir.resolve("pom.xml");
        Files.writeString(pomFile, """
                <project>
                  <dependencies>
                    <dependency>
                      <groupId>com.xuxueli</groupId>
                      <artifactId>xxl-job-core</artifactId>
                      <version>2.2.0</version>
                    </dependency>
                  </dependencies>
                </project>
                """);

        Path javaDir = tempDir.resolve("src/main/java/com/example/task");
        Files.createDirectories(javaDir);
        Path taskClass = javaDir.resolve("ReportCronTask.java");
        Files.writeString(taskClass, """
                package com.example.task;

                import org.springframework.scheduling.annotation.Scheduled;
                import org.springframework.stereotype.Component;

                @Component
                public class ReportCronTask {

                    @Scheduled(cron = "0 0 1 * * ?")
                    public void generateDailyReport() {
                        System.out.println("report");
                    }
                }
                """);

        var result = SpringScheduleAndLockModernizer.modernize(tempDir);
        assertTrue(result.modified());
        assertTrue(result.changesCount() >= 2);

        // 1. Verify @SchedulerLock injected on scheduled method
        String updatedTask = Files.readString(taskClass);
        assertTrue(updatedTask.contains("@SchedulerLock(name = \"generateDailyReportLock\""));
        assertTrue(updatedTask.contains("net.javacrumbs.shedlock.spring.annotation.SchedulerLock"));

        // 2. Verify ShedLockConfiguration generated
        Path generatedConfig = tempDir.resolve("src/main/java/io/elmos/generated/schedule/ShedLockConfiguration.java");
        assertTrue(Files.exists(generatedConfig));
        String generatedContent = Files.readString(generatedConfig);
        assertTrue(generatedContent.contains("EnableSchedulerLock"));
        assertTrue(generatedContent.contains("RedisLockProvider"));

        // 3. Verify pom.xml dependencies
        String updatedPom = Files.readString(pomFile);
        assertTrue(updatedPom.contains("shedlock-spring"));
        assertFalse(updatedPom.contains("2.2.0"));
        assertTrue(updatedPom.contains("2.4.1"));
    }
}
