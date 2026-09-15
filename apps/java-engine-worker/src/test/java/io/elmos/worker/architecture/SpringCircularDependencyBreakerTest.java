package io.elmos.worker.architecture;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class SpringCircularDependencyBreakerTest {

    @TempDir
    Path tempDir;

    @Test
    @DisplayName("Breaks constructor-based circular dependency between ServiceA and ServiceB")
    void testBreaksConstructorCircularDependency() throws IOException {
        Path src = tempDir.resolve("src/main/java/com/example");
        Files.createDirectories(src);

        Path serviceA = src.resolve("ServiceA.java");
        Files.writeString(serviceA, """
                package com.example;

                import org.springframework.stereotype.Service;

                @Service
                public class ServiceA {
                    private final ServiceB serviceB;

                    public ServiceA(ServiceB serviceB) {
                        this.serviceB = serviceB;
                    }
                }
                """, StandardCharsets.UTF_8);

        Path serviceB = src.resolve("ServiceB.java");
        Files.writeString(serviceB, """
                package com.example;

                import org.springframework.stereotype.Service;

                @Service
                public class ServiceB {
                    private final ServiceA serviceA;

                    public ServiceB(ServiceA serviceA) {
                        this.serviceA = serviceA;
                    }
                }
                """, StandardCharsets.UTF_8);

        var result = SpringCircularDependencyBreaker.modernize(tempDir);
        assertTrue(result.modified(), "Must modify project to break circular dependency");
        assertEquals(1, result.changesCount());
        assertFalse(result.cyclesBroken().isEmpty());

        String codeA = Files.readString(serviceA, StandardCharsets.UTF_8);
        String codeB = Files.readString(serviceB, StandardCharsets.UTF_8);

        // One of the services must have @Lazy injected
        boolean aHasLazy = codeA.contains("@Lazy ServiceB serviceB") && codeA.contains("import org.springframework.context.annotation.Lazy;");
        boolean bHasLazy = codeB.contains("@Lazy ServiceA serviceA") && codeB.contains("import org.springframework.context.annotation.Lazy;");
        assertTrue(aHasLazy || bHasLazy, "One service constructor must have @Lazy injected");
    }

    @Test
    @DisplayName("Breaks field-based circular dependency between OrderService and PaymentService")
    void testBreaksFieldCircularDependency() throws IOException {
        Path src = tempDir.resolve("src/main/java/com/example");
        Files.createDirectories(src);

        Path orderService = src.resolve("OrderService.java");
        Files.writeString(orderService, """
                package com.example;

                import org.springframework.stereotype.Service;
                import org.springframework.beans.factory.annotation.Autowired;

                @Service
                public class OrderService {
                    @Autowired
                    private PaymentService paymentService;
                }
                """, StandardCharsets.UTF_8);

        Path paymentService = src.resolve("PaymentService.java");
        Files.writeString(paymentService, """
                package com.example;

                import org.springframework.stereotype.Service;
                import org.springframework.beans.factory.annotation.Autowired;

                @Service
                public class PaymentService {
                    @Autowired
                    private OrderService orderService;
                }
                """, StandardCharsets.UTF_8);

        var result = SpringCircularDependencyBreaker.modernize(tempDir);
        assertTrue(result.modified());
        assertEquals(1, result.changesCount());

        String codeOrder = Files.readString(orderService, StandardCharsets.UTF_8);
        String codePayment = Files.readString(paymentService, StandardCharsets.UTF_8);

        boolean orderHasLazy = codeOrder.contains("@Lazy") && codeOrder.contains("import org.springframework.context.annotation.Lazy;");
        boolean paymentHasLazy = codePayment.contains("@Lazy") && codePayment.contains("import org.springframework.context.annotation.Lazy;");
        assertTrue(orderHasLazy || paymentHasLazy, "One service field must have @Lazy injected");
    }

    @Test
    @DisplayName("Idempotent when @Lazy is already present")
    void testIdempotentWhenAlreadyPresent() {
        String code = """
                package com.example;

                import org.springframework.stereotype.Service;
                import org.springframework.context.annotation.Lazy;

                @Service
                public class ServiceA {
                    public ServiceA(@Lazy ServiceB serviceB) {}
                }
                """;

        String broken = SpringCircularDependencyBreaker.breakDependencyInContent(code, "ServiceA", "ServiceB");
        assertEquals(code, broken);
    }
}
