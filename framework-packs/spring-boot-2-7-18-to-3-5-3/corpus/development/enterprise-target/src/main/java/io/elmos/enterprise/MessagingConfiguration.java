package io.elmos.enterprise;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;

@Configuration
@EnableRabbit
class MessagingConfiguration {
    static final String EXCHANGE = "elmos.enterprise.orders";
    static final String QUEUE = "elmos.enterprise.order-created";
    static final String ROUTING_KEY = "order.created";

    @Bean
    DirectExchange orderExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    Queue orderCreatedQueue() {
        return new Queue(QUEUE, true, false, false);
    }

    @Bean
    Binding orderCreatedBinding(DirectExchange orderExchange, Queue orderCreatedQueue) {
        return BindingBuilder.bind(orderCreatedQueue).to(orderExchange).with(ROUTING_KEY);
    }
}
