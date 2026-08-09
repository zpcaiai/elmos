package sample.orders;

public final class OrderService {
    public Order pay(Order order) {
        if (order.status() != Order.Status.CREATED) {
            throw new IllegalStateException("Only created orders can be paid");
        }
        return new Order(order.id(), order.total(), Order.Status.PAID);
    }
}
