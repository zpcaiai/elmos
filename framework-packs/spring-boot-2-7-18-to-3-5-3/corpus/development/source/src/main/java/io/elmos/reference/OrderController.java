package io.elmos.reference;

import java.util.Map;
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {
    @GetMapping("/{id}")
    Map<String, Object> find(@PathVariable long id) {
        return Map.of(
            "id", id,
            "status", id % 2 == 0 ? "READY" : "REVIEW",
            "amountCents", Math.multiplyExact(id, 125L)
        );
    }

    @PostMapping
    Map<String, String> create(@Valid @RequestBody CreateOrder request) {
        return Map.of("customerId", request.customerId(), "status", "CREATED");
    }

    record CreateOrder(@NotBlank String customerId) {}
}
