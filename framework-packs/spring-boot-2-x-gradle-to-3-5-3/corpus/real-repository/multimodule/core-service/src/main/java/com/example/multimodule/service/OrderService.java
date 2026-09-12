package com.example.multimodule.service;

import com.example.multimodule.domain.OrderDto;

public class OrderService {
    public OrderDto processOrder(String id, double amount) {
        return new OrderDto(id, amount, "PROCESSED");
    }
}
