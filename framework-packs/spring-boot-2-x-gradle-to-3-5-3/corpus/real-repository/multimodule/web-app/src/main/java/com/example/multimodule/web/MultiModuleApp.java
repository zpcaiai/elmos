package com.example.multimodule.web;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(scanBasePackages = "com.example.multimodule")
public class MultiModuleApp {
    public static void main(String[] args) {
        SpringApplication.run(MultiModuleApp.class, args);
    }
}
