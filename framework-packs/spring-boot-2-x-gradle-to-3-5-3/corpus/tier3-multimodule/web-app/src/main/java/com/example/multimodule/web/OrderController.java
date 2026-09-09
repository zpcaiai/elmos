package com.example.multimodule.web;

import com.example.multimodule.domain.OrderDto;
import com.example.multimodule.service.OrderService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {
    private final OrderService orderService = new OrderService();

    @GetMapping("/api/orders/{id}")
    public OrderDto getOrder(@PathVariable String id) {
        return orderService.processOrder(id, 99.9);
    }
}
