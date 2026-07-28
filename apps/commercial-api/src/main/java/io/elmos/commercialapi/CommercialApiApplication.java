package io.elmos.commercialapi;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.flyway.FlywayAutoConfiguration;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

@SpringBootApplication(
        scanBasePackages = {"io.elmos.commercialapi", "io.elmos.commercialadapter"},
        exclude = {DataSourceAutoConfiguration.class, FlywayAutoConfiguration.class}
)
public class CommercialApiApplication {
    public static void main(String[] args) { SpringApplication.run(CommercialApiApplication.class, args); }
}
