package io.elmos.liveworkbench;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@EnableScheduling
@SpringBootApplication
public class LiveWorkbenchApplication {
    public static void main(String[] args) {
        SpringApplication.run(LiveWorkbenchApplication.class, args);
    }
}
