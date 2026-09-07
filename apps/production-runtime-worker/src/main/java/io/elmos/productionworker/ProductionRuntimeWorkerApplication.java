package io.elmos.productionworker;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class ProductionRuntimeWorkerApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProductionRuntimeWorkerApplication.class, args);
    }
}
