package io.elmos.workspaceservice;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(scanBasePackages = "io.elmos")
public class WorkspaceServiceApplication {
    public static void main(String[] args) { SpringApplication.run(WorkspaceServiceApplication.class, args); }
}
