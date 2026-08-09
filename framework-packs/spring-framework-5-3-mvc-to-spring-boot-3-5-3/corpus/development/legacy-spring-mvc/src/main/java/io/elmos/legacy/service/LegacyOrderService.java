package io.elmos.legacy.service;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class LegacyOrderService {
    private final String currency;

    public LegacyOrderService(@Value("${legacy.orders.currency}") String currency) {
        this.currency = currency;
    }

    public Map<String, Object> find(long id) {
        Map<String, Object> order = new LinkedHashMap<>();
        order.put("id", id);
        order.put("status", id % 2 == 0 ? "READY" : "REVIEW");
        order.put("amountCents", Math.multiplyExact(id, 125L));
        order.put("currency", currency);
        return order;
    }
}
