package io.elmos.transformer;

import io.elmos.worker.EphemeralTransformerController;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;

import java.time.Clock;

@SpringBootApplication
@Import(EphemeralTransformerController.class)
public class JavaEngineTransformerApplication {
    public static void main(String[] args) {
        SpringApplication.run(JavaEngineTransformerApplication.class, args);
    }

    @Bean
    Clock transformerClock() {
        return Clock.systemUTC();
    }
}
