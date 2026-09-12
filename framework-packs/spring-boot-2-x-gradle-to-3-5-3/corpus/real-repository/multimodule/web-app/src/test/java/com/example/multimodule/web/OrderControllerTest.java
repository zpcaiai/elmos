package com.example.multimodule.web;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

public class OrderControllerTest {
    @Test
    void controllerCallsService() {
        OrderController controller = new OrderController();
        var order = controller.getOrder("ORD-1001");
        assertEquals("ORD-1001", order.orderId());
        assertEquals("PROCESSED", order.status());
    }
}
