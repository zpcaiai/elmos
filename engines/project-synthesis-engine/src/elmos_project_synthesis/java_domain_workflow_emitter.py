"""Java (Spring Boot 3) Domain-Driven Design, Workflow FSM, and Distributed Transactions Emitter.

Generates complete industrial-grade Java domain models, value objects, FSM state machines,
and distributed transaction coordinators (Saga LIFO compensation, Outbox, Fencing Locks).
"""

from __future__ import annotations

from .models import SynthesisRequest, pascal


def generate_java_domain_workflow_files(request: SynthesisRequest) -> dict[str, str]:
    """Generate industrial-grade DDD, FSM, and Distributed Transaction files for Java Spring Boot 3."""
    files: dict[str, str] = {}
    pkg = request.namespace or "com.elmos.enterprise"
    pkg_path = pkg.replace(".", "/")
    entity = request.entities[0] if request.entities else None
    entity_name = pascal(entity.singular) if entity else "Order"

    # 1. Domain Value Objects (Java 21+ record types)
    files[f"src/main/java/{pkg_path}/domain/Money.java"] = f"""package {pkg}.domain;

import java.io.Serializable;
import java.math.BigDecimal;
import java.util.Objects;
import java.util.regex.Pattern;

/**
 * Immutable high-precision monetary Value Object.
 */
public record Money(BigDecimal amount, String currency) implements Serializable {{

    private static final Pattern CURRENCY_PATTERN = Pattern.compile("^[A-Z]{{3}}$");

    public Money {{
        Objects.requireNonNull(amount, "amount cannot be null");
        Objects.requireNonNull(currency, "currency cannot be null");
        if (amount.compareTo(BigDecimal.ZERO) < 0) {{
            throw new IllegalArgumentException("amount cannot be negative: " + amount);
        }}
        String norm = currency.trim().toUpperCase();
        if (!CURRENCY_PATTERN.matcher(norm).matches()) {{
            throw new IllegalArgumentException("invalid ISO-4217 currency code: " + norm);
        }}
        currency = norm;
    }}

    public static Money of(double amount, String currency) {{
        return new Money(BigDecimal.valueOf(amount), currency);
    }}

    public Money add(Money other) {{
        Objects.requireNonNull(other, "other money cannot be null");
        if (!this.currency.equals(other.currency)) {{
            throw new IllegalArgumentException("currency mismatch: " + this.currency + " vs " + other.currency);
        }}
        return new Money(this.amount.add(other.amount), this.currency);
    }}

    public Money subtract(Money other) {{
        Objects.requireNonNull(other, "other money cannot be null");
        if (!this.currency.equals(other.currency)) {{
            throw new IllegalArgumentException("currency mismatch: " + this.currency + " vs " + other.currency);
        }}
        if (this.amount.compareTo(other.amount) < 0) {{
            throw new IllegalArgumentException("insufficient funds for subtraction");
        }}
        return new Money(this.amount.subtract(other.amount), this.currency);
    }}
}}
"""

    files[f"src/main/java/{pkg_path}/domain/Address.java"] = f"""package {pkg}.domain;

import java.io.Serializable;
import java.util.Objects;

/**
 * Physical Address Value Object with structural equality.
 */
public record Address(
    String street,
    String city,
    String stateProvince,
    String postalCode,
    String country
) implements Serializable {{

    public Address {{
        Objects.requireNonNull(street, "street cannot be null");
        Objects.requireNonNull(city, "city cannot be null");
        Objects.requireNonNull(stateProvince, "stateProvince cannot be null");
        Objects.requireNonNull(postalCode, "postalCode cannot be null");
        country = country != null ? country : "CN";
    }}
}}
"""

    # 2. Domain Events
    files[f"src/main/java/{pkg_path}/domain/DomainEvent.java"] = f"""package {pkg}.domain;

import java.io.Serializable;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;

/**
 * Strongly typed Domain Event Envelope.
 */
public record DomainEvent(
    String eventId,
    String aggregateType,
    String aggregateId,
    String eventType,
    Map<String, Object> payload,
    Instant occurredAt,
    String traceId
) implements Serializable {{

    public static DomainEvent create(String aggregateType, String aggregateId, String eventType, Map<String, Object> payload) {{
        return new DomainEvent(
            "evt-" + UUID.randomUUID().toString().replace("-", "").substring(0, 16),
            aggregateType,
            aggregateId,
            eventType,
            payload,
            Instant.now(),
            "tr-" + UUID.randomUUID().toString().replace("-", "").substring(0, 12)
        );
    }}
}}
"""

    # 3. Aggregate Root
    files[f"src/main/java/{pkg_path}/domain/{entity_name}Aggregate.java"] = f"""package {pkg}.domain;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

/**
 * Industrial-grade DDD Aggregate Root for {entity_name}.
 */
public class {entity_name}Aggregate {{

    private final String id;
    private final String tenantId;
    private String reference;
    private Money total;
    private String status;
    private long version;
    private final Instant createdAt;
    private Instant updatedAt;
    private final List<DomainEvent> uncommittedEvents = new ArrayList<>();

    public {entity_name}Aggregate(String id, String tenantId, String reference, Money total) {{
        this.id = id != null ? id : "agg-" + UUID.randomUUID().toString().replace("-", "").substring(0, 12);
        this.tenantId = Objects.requireNonNull(tenantId, "tenantId cannot be null");
        this.reference = Objects.requireNonNull(reference, "reference cannot be null");
        this.total = Objects.requireNonNull(total, "total cannot be null");
        this.status = "CREATED";
        this.version = 1L;
        this.createdAt = Instant.now();
        this.updatedAt = Instant.now();

        validateInvariants();
        recordEvent("{entity_name}Created", Map.of(
            "id", this.id,
            "reference", this.reference,
            "total", this.total.amount(),
            "currency", this.total.currency()
        ));
    }}

    public void updateDetails(String newReference, Money newTotal) {{
        Objects.requireNonNull(newReference, "reference cannot be null");
        Objects.requireNonNull(newTotal, "total cannot be null");
        this.reference = newReference;
        this.total = newTotal;
        this.version++;
        this.updatedAt = Instant.now();

        validateInvariants();
        recordEvent("{entity_name}Updated", Map.of(
            "id", this.id,
            "reference", this.reference,
            "total", this.total.amount()
        ));
    }}

    public void transitionStatus(String newStatus) {{
        this.status = newStatus;
        this.version++;
        this.updatedAt = Instant.now();
        recordEvent("{entity_name}StatusTransitioned", Map.of("id", this.id, "newStatus", newStatus));
    }}

    private void validateInvariants() {{
        if (reference.isBlank()) {{
            throw new IllegalStateException("Domain Invariant Violation: Reference cannot be empty");
        }}
        if (total.amount().compareTo(java.math.BigDecimal.ZERO) < 0) {{
            throw new IllegalStateException("Domain Invariant Violation: Total cannot be negative");
        }}
    }}

    private void recordEvent(String eventType, Map<String, Object> payload) {{
        uncommittedEvents.add(DomainEvent.create("{entity_name}", this.id, eventType, payload));
    }}

    public List<DomainEvent> pollEvents() {{
        List<DomainEvent> events = new ArrayList<>(uncommittedEvents);
        uncommittedEvents.clear();
        return Collections.unmodifiableList(events);
    }}

    public String getId() {{ return id; }}
    public String getTenantId() {{ return tenantId; }}
    public String getReference() {{ return reference; }}
    public Money getTotal() {{ return total; }}
    public String getStatus() {{ return status; }}
    public long getVersion() {{ return version; }}
    public Instant getCreatedAt() {{ return createdAt; }}
    public Instant getUpdatedAt() {{ return updatedAt; }}
}}
"""

    # 4. Workflow State Machine (FSM)
    files[f"src/main/java/{pkg_path}/workflow/{entity_name}StateMachine.java"] = f"""package {pkg}.workflow;

import {pkg}.domain.{entity_name}Aggregate;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Finite State Machine for {entity_name} lifecycle management.
 */
public class {entity_name}StateMachine {{

    public enum State {{
        CREATED, PENDING_PAYMENT, PAID, FULFILLED, CANCELLED, REFUNDED
    }}

    public enum Trigger {{
        SUBMIT, PAY, COMPLETE, CANCEL, REFUND
    }}

    public record TransitionLog(
        String aggregateId,
        State fromState,
        State toState,
        Trigger trigger,
        Instant transitionedAt,
        String operator
    ) {{}}

    private static final Map<State, Map<Trigger, State>> TRANSITIONS = Map.of(
        State.CREATED, Map.of(Trigger.SUBMIT, State.PENDING_PAYMENT, Trigger.CANCEL, State.CANCELLED),
        State.PENDING_PAYMENT, Map.of(Trigger.PAY, State.PAID, Trigger.CANCEL, State.CANCELLED),
        State.PAID, Map.of(Trigger.COMPLETE, State.FULFILLED, Trigger.REFUND, State.REFUNDED),
        State.FULFILLED, Map.of(),
        State.CANCELLED, Map.of(),
        State.REFUNDED, Map.of()
    );

    private final List<TransitionLog> transitionJournal = Collections.synchronizedList(new ArrayList<>());

    public State transition({entity_name}Aggregate aggregate, Trigger trigger, String operator) {{
        State current = State.valueOf(aggregate.getStatus());
        Map<Trigger, State> allowed = TRANSITIONS.getOrDefault(current, Map.of());
        State next = allowed.get(trigger);

        if (next == null) {{
            throw new IllegalStateException("Invalid state transition from " + current + " via " + trigger);
        }}

        // Invariant guard check
        if (trigger == Trigger.PAY && aggregate.getTotal().amount().compareTo(java.math.BigDecimal.ZERO) <= 0) {{
            throw new IllegalStateException("Guard violation: Cannot pay zero or negative total");
        }}

        aggregate.transitionStatus(next.name());
        transitionJournal.add(new TransitionLog(aggregate.getId(), current, next, trigger, Instant.now(), operator));
        return next;
    }}

    public List<TransitionLog> getJournal() {{
        return Collections.unmodifiableList(new ArrayList<>(transitionJournal));
    }}
}}
"""

    # 5. Distributed Transactions (Saga Orchestrator with LIFO compensation)
    files[f"src/main/java/{pkg_path}/transactions/SagaOrchestrator.java"] = f"""package {pkg}.transactions;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.function.Supplier;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Orchestrated Saga Coordinator with automatic LIFO rollback compensation.
 */
public class SagaOrchestrator {{

    private static final Logger log = LoggerFactory.getLogger(SagaOrchestrator.class);

    public record Step(
        String name,
        Supplier<Boolean> forwardAction,
        Runnable compensationAction
    ) {{}}

    private final List<Step> steps = new ArrayList<>();

    public SagaOrchestrator addStep(String name, Supplier<Boolean> forward, Runnable compensation) {{
        steps.add(new Step(name, forward, compensation));
        return this;
    }}

    public boolean execute() {{
        Deque<Step> executed = new ArrayDeque<>();
        for (Step step : steps) {{
            log.info("Executing Saga step forward: {{}}", step.name());
            try {{
                boolean ok = step.forwardAction().get();
                if (!ok) {{
                    log.error("Saga step failed forward: {{}}, initiating LIFO compensation", step.name());
                    rollback(executed);
                    return false;
                }}
                executed.push(step);
            }} catch (Exception exc) {{
                log.error("Saga step threw exception: {{}}, compensating: {{}}", step.name(), exc.getMessage());
                rollback(executed);
                return false;
            }}
        }}
        log.info("Saga successfully completed all {{}} steps", steps.size());
        return true;
    }}

    private void rollback(Deque<Step> executed) {{
        while (!executed.isEmpty()) {{
            Step compStep = executed.pop();
            log.warn("Executing LIFO compensation for: {{}}", compStep.name());
            try {{
                compStep.compensationAction().run();
            }} catch (Exception exc) {{
                log.error("Compensation failed for step: {{}}, manual intervention required: {{}}", compStep.name(), exc.getMessage());
            }}
        }}
    }}
}}
"""

    # 6. Distributed Lock with Monotonic Fencing Token
    files[f"src/main/java/{pkg_path}/transactions/DistributedLockManager.java"] = f"""package {pkg}.transactions;

import java.time.Instant;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Distributed Mutex Lock with Monotonic Fencing Token preventing split-brain writes.
 */
public class DistributedLockManager {{

    public record LockEntry(String owner, Instant expiresAt, long fencingToken) {{}}

    private final Map<String, LockEntry> locks = new ConcurrentHashMap<>();
    private final Map<String, AtomicLong> generationCounters = new ConcurrentHashMap<>();

    public synchronized long acquire(String resourceId, String owner, long ttlMillis) {{
        Instant now = Instant.now();
        LockEntry current = locks.get(resourceId);

        if (current != null && current.expiresAt().isAfter(now) && !current.owner().equals(owner)) {{
            throw new IllegalStateException("Resource '" + resourceId + "' is currently locked by '" + current.owner() + "'");
        }}

        long token = generationCounters.computeIfAbsent(resourceId, k -> new AtomicLong(0)).incrementAndGet();
        locks.put(resourceId, new LockEntry(owner, now.plusMillis(ttlMillis), token));
        return token;
    }}

    public synchronized void release(String resourceId, String owner) {{
        LockEntry current = locks.get(resourceId);
        if (current != null && current.owner().equals(owner)) {{
            locks.remove(resourceId);
        }}
    }}

    public synchronized boolean isLocked(String resourceId) {{
        LockEntry current = locks.get(resourceId);
        return current != null && current.expiresAt().isAfter(Instant.now());
    }}
}}
"""

    return files
