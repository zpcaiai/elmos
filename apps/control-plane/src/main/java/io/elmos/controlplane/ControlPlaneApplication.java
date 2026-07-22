package io.elmos.controlplane;

import io.elmos.application.BatchOneDemoService;
import io.elmos.application.DemoPersistencePort;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

import java.time.Clock;

@SpringBootApplication(scanBasePackages = "io.elmos")
public class ControlPlaneApplication {
    public static void main(String[] args) { SpringApplication.run(ControlPlaneApplication.class,args); }
    @Bean Clock systemClock(){return Clock.systemUTC();}
    @Bean BatchOneDemoService demoService(DemoPersistencePort persistence,Clock clock){return new BatchOneDemoService(persistence,clock);}
}

