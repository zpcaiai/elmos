package io.elmos.enterprise;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/enterprise/orders")
class EnterpriseController {
    private final EnterpriseOrderService orderService;

    EnterpriseController(EnterpriseOrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    @PreAuthorize("hasRole('OPERATOR')")
    OrderView create(@Valid @RequestBody CreateOrder request) {
        return orderService.create(request.requestId(), request.amountCents(), false);
    }

    @GetMapping("/{requestId}")
    @PreAuthorize("hasAnyRole('OPERATOR', 'VIEWER')")
    OrderView find(@PathVariable String requestId) {
        return orderService.findByRequestId(requestId);
    }

    record CreateOrder(@NotBlank String requestId, @Positive long amountCents) {}
}
