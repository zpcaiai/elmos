package io.elmos.enterprise;

import static org.hamcrest.Matchers.is;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.rabbit.core.RabbitAdmin;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureMockMvc
@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class EnterpriseContractIT {
    private static final String POSTGRES_DIGEST =
        "postgres@sha256:6567bca8d7bc8c82c5922425a0baee57be8402df92bae5eacad5f01ae9544daa";
    private static final String RABBIT_DIGEST =
        "rabbitmq@sha256:5cbd7145b0306399ad68422c3350b6cbd1bb95704b39f5896480e5b6d4238a04";
    private static final String OPERATOR_PASSWORD = "test-only-operator-password";
    private static final String VIEWER_PASSWORD = "test-only-viewer-password";
    private static final String ADMIN_PASSWORD = "test-only-admin-password";

    @Container
    static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>(
        DockerImageName.parse(POSTGRES_DIGEST).asCompatibleSubstituteFor("postgres"))
        .withDatabaseName("spring_enterprise")
        .withUsername("spring_enterprise")
        .withPassword("test-only-database-password");

    @Container
    static final RabbitMQContainer RABBIT = new RabbitMQContainer(
        DockerImageName.parse(RABBIT_DIGEST).asCompatibleSubstituteFor("rabbitmq"))
        .withAdminUser("spring_enterprise")
        .withAdminPassword("test-only-broker-password");

    @DynamicPropertySource
    static void runtimeProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
        registry.add("spring.rabbitmq.host", RABBIT::getHost);
        registry.add("spring.rabbitmq.port", RABBIT::getAmqpPort);
        registry.add("spring.rabbitmq.username", RABBIT::getAdminUsername);
        registry.add("spring.rabbitmq.password", RABBIT::getAdminPassword);
        registry.add("enterprise.security.operator-password", () -> OPERATOR_PASSWORD);
        registry.add("enterprise.security.viewer-password", () -> VIEWER_PASSWORD);
        registry.add("enterprise.security.admin-password", () -> ADMIN_PASSWORD);
    }

    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;
    @Autowired EnterpriseOrderService orderService;
    @Autowired OutboxRelay outboxRelay;
    @Autowired RabbitTemplate rabbitTemplate;
    @Autowired RabbitAdmin rabbitAdmin;
    @Autowired TestRestTemplate liveHttp;
    @Value("${local.server.port}") int livePort;

    private ExecutorService executor;

    @BeforeEach
    void resetState() {
        rabbitAdmin.purgeQueue(MessagingConfiguration.QUEUE, false);
        jdbc.update("delete from enterprise_consumed_events");
        jdbc.update("delete from enterprise_outbox");
        jdbc.update("delete from enterprise_orders");
        jdbc.update("delete from enterprise_inventory");
        jdbc.update("insert into enterprise_inventory (sku, available) values ('sku-1', 10)");
    }

    @AfterEach
    void stopExecutor() {
        if (executor != null) {
            executor.shutdownNow();
        }
    }

    @Test
    void transactionRollbackRemovesOrderAndOutboxTogether() {
        IllegalStateException failure = assertThrows(
            IllegalStateException.class,
            () -> orderService.create("rollback-request", 1250, true));
        assertEquals("FORCED_TRANSACTION_ROLLBACK", failure.getMessage());
        assertEquals(0L, count("enterprise_orders"));
        assertEquals(0L, count("enterprise_outbox"));
    }

    @Test
    void pessimisticInventoryLockPreventsOversell() throws Exception {
        executor = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);
        Callable<Boolean> reservation = () -> {
            start.await();
            try {
                orderService.reserveInventory("sku-1", 7);
                return true;
            } catch (IllegalStateException expected) {
                assertEquals("INVENTORY_NOT_AVAILABLE", expected.getMessage());
                return false;
            }
        };
        List<Future<Boolean>> futures = new ArrayList<>();
        futures.add(executor.submit(reservation));
        futures.add(executor.submit(reservation));
        start.countDown();

        int successes = 0;
        for (Future<Boolean> future : futures) {
            if (future.get()) {
                successes++;
            }
        }
        assertEquals(1, successes);
        assertEquals(3L, jdbc.queryForObject(
            "select available from enterprise_inventory where sku = 'sku-1'", Long.class));
    }

    @Test
    void confirmedOutboxDeliveryIsIdempotentAtConsumer() throws Exception {
        OrderView order = orderService.create("message-request", 5250, false);
        assertEquals(1, outboxRelay.publishPending());
        awaitCount("enterprise_consumed_events", 1);

        String messageId = jdbc.queryForObject("select id from enterprise_outbox", String.class);
        String payload = jdbc.queryForObject("select payload from enterprise_outbox", String.class);
        rabbitTemplate.convertAndSend(
            MessagingConfiguration.EXCHANGE,
            MessagingConfiguration.ROUTING_KEY,
            payload,
            message -> {
                message.getMessageProperties().setMessageId(messageId);
                return message;
            });
        awaitQueueDrain();

        assertEquals(1L, count("enterprise_consumed_events"));
        assertEquals(1, jdbc.queryForObject(
            "select handled_count from enterprise_consumed_events where message_id = ?",
            Integer.class,
            messageId));
        assertTrue(jdbc.queryForObject(
            "select published from enterprise_outbox where aggregate_id = ?", Boolean.class, order.id()));
    }

    @Test
    void webSecurityValidationAndActuatorBoundariesHold() throws Exception {
        mvc.perform(post("/api/enterprise/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"requestId\":\"web-request\",\"amountCents\":1250}"))
            .andExpect(status().isUnauthorized());
        mvc.perform(post("/api/enterprise/orders")
                .with(httpBasic("viewer", VIEWER_PASSWORD))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"requestId\":\"web-request\",\"amountCents\":1250}"))
            .andExpect(status().isForbidden());
        mvc.perform(post("/api/enterprise/orders")
                .with(httpBasic("operator", OPERATOR_PASSWORD))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"requestId\":\"web-request\",\"amountCents\":1250}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.requestId", is("web-request")))
            .andExpect(jsonPath("$.status", is("CREATED")));
        mvc.perform(get("/api/enterprise/orders/web-request"))
            .andExpect(status().isUnauthorized());
        mvc.perform(get("/api/enterprise/orders/web-request")
                .with(httpBasic("viewer", VIEWER_PASSWORD)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.requestId", is("web-request")))
            .andExpect(jsonPath("$.amountCents", is(1250)));
        mvc.perform(get("/actuator/health"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status", is("UP")));
        mvc.perform(get("/actuator/metrics").with(httpBasic("operator", OPERATOR_PASSWORD)))
            .andExpect(status().isForbidden());
        mvc.perform(get("/actuator/metrics").with(httpBasic("admin", ADMIN_PASSWORD)))
            .andExpect(status().isOk());

        String base = "http://127.0.0.1:" + livePort;
        assertEquals(
            HttpStatus.OK,
            liveHttp.getForEntity(base + "/actuator/health", String.class).getStatusCode());
        assertEquals(
            HttpStatus.OK,
            liveHttp.withBasicAuth("viewer", VIEWER_PASSWORD)
                .getForEntity(base + "/api/enterprise/orders/web-request", String.class)
                .getStatusCode());
    }

    private long count(String table) {
        return jdbc.queryForObject("select count(*) from " + table, Long.class);
    }

    private void awaitCount(String table, long expected) throws InterruptedException {
        Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
        while (Instant.now().isBefore(deadline)) {
            if (count(table) == expected) {
                return;
            }
            Thread.sleep(100);
        }
        assertEquals(expected, count(table));
    }

    private void awaitQueueDrain() throws InterruptedException {
        Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
        while (Instant.now().isBefore(deadline)) {
            Object count = rabbitAdmin.getQueueProperties(MessagingConfiguration.QUEUE)
                .get(RabbitAdmin.QUEUE_MESSAGE_COUNT);
            if (Integer.valueOf(0).equals(count)) {
                Thread.sleep(250);
                return;
            }
            Thread.sleep(100);
        }
        throw new AssertionError("RabbitMQ queue did not drain");
    }
}
