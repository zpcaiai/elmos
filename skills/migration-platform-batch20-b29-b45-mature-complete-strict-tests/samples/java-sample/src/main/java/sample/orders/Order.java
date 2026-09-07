package sample.orders;

import java.math.BigDecimal;

public record Order(String id, BigDecimal total, Status status) {
    public enum Status { CREATED, PAID, CANCELLED }
}
