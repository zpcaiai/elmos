package com.example.starter;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertNotNull;

public class StarterApplicationTest {
    @Test
    void contextLoads() {
        assertNotNull(new HelloController().hello());
    }
}
