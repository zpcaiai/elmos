package io.elmos.commercialapi;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(
        scanBasePackages = {"io.elmos.commercialapi", "io.elmos.commercialadapter"}
)
public class CommercialApiApplication {
    public static void main(String[] args) { SpringApplication.run(CommercialApiApplication.class, args); }
}
