package io.elmos.legacy.web;

import io.elmos.legacy.service.LegacyOrderService;
import java.net.URI;
import java.util.LinkedHashMap;
import java.util.Map;
import javax.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
@RequestMapping
public class LegacyOrderController {
    private final LegacyOrderService orders;

    public LegacyOrderController(LegacyOrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/api/orders/{id}")
    @ResponseBody
    public Map<String, Object> find(@PathVariable long id) {
        return orders.find(id);
    }

    @PostMapping("/api/orders")
    @ResponseBody
    public ResponseEntity<Map<String, Object>> create(@Valid @RequestBody LegacyOrderForm form) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("customerId", form.getCustomerId());
        body.put("amountCents", form.getAmountCents());
        body.put("status", "CREATED");
        return ResponseEntity.created(URI.create("/api/orders/1001")).body(body);
    }

    @GetMapping("/orders")
    public String list(Model model) {
        model.addAttribute("title", "Legacy orders");
        return "orders/list";
    }
}
