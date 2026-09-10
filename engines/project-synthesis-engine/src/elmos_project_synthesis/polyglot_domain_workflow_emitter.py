"""Polyglot (Kotlin & PHP) Domain-Driven Design, Workflow FSM, and Distributed Transactions Emitter.

Generates complete industrial-grade Kotlin (Spring Boot) and PHP (Laravel 11) domain models,
value objects, FSM state machines, and distributed transaction coordinators.
"""
from __future__ import annotations

from typing import Dict
from .models import SynthesisRequest, pascal


def generate_kotlin_domain_workflow_files(request: SynthesisRequest) -> Dict[str, str]:
    """Generate industrial-grade DDD, FSM, and Distributed Transaction files for Kotlin Spring Boot."""
    files: Dict[str, str] = {}
    pkg = request.namespace or "com.elmos.enterprise"
    pkg_path = pkg.replace(".", "/")
    entity = request.entities[0] if request.entities else None
    entity_name = pascal(entity.singular) if entity else "Order"

    # 1. Value Objects
    files[f"src/main/kotlin/{pkg_path}/domain/ValueObjects.kt"] = f"""package {pkg}.domain

import java.math.BigDecimal
import java.util.regex.Pattern

private val CURRENCY_PATTERN = Pattern.compile("^[A-Z]{{3}}$")

/**
 * Immutable high-precision monetary Value Object in Kotlin.
 */
data class Money(val amount: BigDecimal, val currency: String) {{
    init {{
        require(amount >= BigDecimal.ZERO) {{ "Amount cannot be negative: $amount" }}
        val norm = currency.trim().uppercase()
        require(CURRENCY_PATTERN.matcher(norm).matches()) {{ "Invalid ISO-4217 currency: $norm" }}
    }}

    operator fun plus(other: Money): Money {{
        require(currency == other.currency) {{ "Currency mismatch: $currency vs ${{other.currency}}" }}
        return Money(amount + other.amount, currency)
    }}

    operator fun minus(other: Money): Money {{
        require(currency == other.currency) {{ "Currency mismatch: $currency vs ${{other.currency}}" }}
        require(amount >= other.amount) {{ "Insufficient funds for subtraction" }}
        return Money(amount - other.amount, currency)
    }}
}}

data class Address(
    val street: String,
    val city: String,
    val stateProvince: String,
    val postalCode: String,
    val country: String = "CN"
)

data class Quantity(val value: BigDecimal, val unit: String)
"""

    # 2. Domain Events
    files[f"src/main/kotlin/{pkg_path}/domain/DomainEvent.kt"] = f"""package {pkg}.domain

import java.time.Instant
import java.util.UUID

data class DomainEvent(
    val eventId: String = "evt-" + UUID.randomUUID().toString().replace("-", "").take(16),
    val aggregateType: String,
    val aggregateId: String,
    val eventType: String,
    val payload: Map<String, Any?>,
    val occurredAt: Instant = Instant.now(),
    val traceId: String = "tr-" + UUID.randomUUID().toString().replace("-", "").take(12)
)
"""

    # 3. Aggregate Root
    files[f"src/main/kotlin/{pkg_path}/domain/{entity_name}Aggregate.kt"] = f"""package {pkg}.domain

import java.math.BigDecimal
import java.time.Instant
import java.util.UUID

class {entity_name}Aggregate(
    val id: String = "agg-" + UUID.randomUUID().toString().replace("-", "").take(12),
    val tenantId: String,
    var reference: String,
    var total: Money
) {{
    var status: String = "CREATED"
        private set
    var version: Long = 1L
        private set
    val createdAt: Instant = Instant.now()
    var updatedAt: Instant = Instant.now()
        private set

    private val uncommittedEvents = mutableListOf<DomainEvent>()

    init {{
        validateInvariants()
        recordEvent("{entity_name}Created", mapOf(
            "id" to id,
            "reference" to reference,
            "total" to total.amount,
            "currency" to total.currency
        ))
    }}

    fun updateDetails(newReference: String, newTotal: Money) {{
        reference = newReference
        total = newTotal
        version++
        updatedAt = Instant.now()
        validateInvariants()
        recordEvent("{entity_name}Updated", mapOf(
            "id" to id,
            "reference" to reference,
            "total" to total.amount
        ))
    }}

    fun transitionStatus(newStatus: String) {{
        status = newStatus
        version++
        updatedAt = Instant.now()
        recordEvent("{entity_name}StatusTransitioned", mapOf("id" to id, "newStatus" to newStatus))
    }}

    private fun validateInvariants() {{
        check(reference.isNotBlank()) {{ "Domain Invariant Violation: Reference cannot be blank" }}
        check(total.amount >= BigDecimal.ZERO) {{ "Domain Invariant Violation: Total cannot be negative" }}
    }}

    private fun recordEvent(eventType: String, payload: Map<String, Any?>) {{
        uncommittedEvents.add(DomainEvent(
            aggregateType = "{entity_name}",
            aggregateId = id,
            eventType = eventType,
            payload = payload
        ))
    }}

    fun pollEvents(): List<DomainEvent> {{
        val events = uncommittedEvents.toList()
        uncommittedEvents.clear()
        return events
    }}
}}
"""

    # 4. Workflow State Machine (FSM)
    files[f"src/main/kotlin/{pkg_path}/workflow/{entity_name}StateMachine.kt"] = f"""package {pkg}.workflow

import {pkg}.domain.{entity_name}Aggregate
import java.math.BigDecimal
import java.time.Instant
import java.util.concurrent.CopyOnWriteArrayList

enum class OrderState {{
    CREATED, PENDING_PAYMENT, PAID, FULFILLED, CANCELLED, REFUNDED
}}

enum class OrderTrigger {{
    SUBMIT, PAY, COMPLETE, CANCEL, REFUND
}}

data class StateTransitionLog(
    val aggregateId: String,
    val fromState: OrderState,
    val toState: OrderState,
    val trigger: OrderTrigger,
    val transitionedAt: Instant = Instant.now(),
    val operator: String
)

class {entity_name}StateMachine {{
    private val journal = CopyOnWriteArrayList<StateTransitionLog>()

    fun transition(aggregate: {entity_name}Aggregate, trigger: OrderTrigger, operator: String): OrderState {{
        val current = OrderState.valueOf(aggregate.status)
        val next = when (current) {{
            OrderState.CREATED -> when (trigger) {{
                OrderTrigger.SUBMIT -> OrderState.PENDING_PAYMENT
                OrderTrigger.CANCEL -> OrderState.CANCELLED
                else -> throw IllegalStateException("Invalid trigger $trigger from $current")
            }}
            OrderState.PENDING_PAYMENT -> when (trigger) {{
                OrderTrigger.PAY -> OrderState.PAID
                OrderTrigger.CANCEL -> OrderState.CANCELLED
                else -> throw IllegalStateException("Invalid trigger $trigger from $current")
            }}
            OrderState.PAID -> when (trigger) {{
                OrderTrigger.COMPLETE -> OrderState.FULFILLED
                OrderTrigger.REFUND -> OrderState.REFUNDED
                else -> throw IllegalStateException("Invalid trigger $trigger from $current")
            }}
            else -> throw IllegalStateException("Cannot transition from terminal state $current")
        }}

        if (trigger == OrderTrigger.PAY && aggregate.total.amount <= BigDecimal.ZERO) {{
            throw IllegalStateException("Guard violation: Cannot pay zero or negative total")
        }}

        aggregate.transitionStatus(next.name)
        journal.add(StateTransitionLog(aggregate.id, current, next, trigger, Instant.now(), operator))
        return next
    }}

    fun getJournal(): List<StateTransitionLog> = journal.toList()
}}
"""

    # 5. Distributed Transactions (Saga Orchestrator)
    files[f"src/main/kotlin/{pkg_path}/transactions/SagaOrchestrator.kt"] = f"""package {pkg}.transactions

import java.util.ArrayDeque

data class SagaStep(
    val name: String,
    val forward: () -> Boolean,
    val compensation: () -> Unit
)

class SagaOrchestrator {{
    private val steps = mutableListOf<SagaStep>()

    fun addStep(name: String, forward: () -> Boolean, compensation: () -> Unit): SagaOrchestrator {{
        steps.add(SagaStep(name, forward, compensation))
        return this
    }}

    fun execute(): Boolean {{
        val executed = ArrayDeque<SagaStep>()
        for (step in steps) {{
            try {{
                val ok = step.forward()
                if (!ok) {{
                    rollback(executed)
                    return false
                }}
                executed.push(step)
            }} catch (e: Exception) {{
                rollback(executed)
                return false
            }}
        }}
        return true
    }}

    private fun rollback(executed: ArrayDeque<SagaStep>) {{
        while (executed.isNotEmpty()) {{
            val step = executed.pop()
            try {{
                step.compensation()
            }} catch (_: Exception) {{
            }}
        }}
    }}
}}
"""

    # 6. Distributed Lock with Monotonic Fencing Token
    files[f"src/main/kotlin/{pkg_path}/transactions/DistributedLockManager.kt"] = f"""package {pkg}.transactions

import java.time.Instant
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicLong

data class LockEntry(val owner: String, val expiresAt: Instant, val fencingToken: Long)

class DistributedLockManager {{
    private val locks = ConcurrentHashMap<String, LockEntry>()
    private val counters = ConcurrentHashMap<String, AtomicLong>()

    @Synchronized
    fun acquire(resourceId: String, owner: String, ttlMillis: Long): Long {{
        val now = Instant.now()
        val current = locks[resourceId]
        if (current != null && current.expiresAt.isAfter(now) && current.owner != owner) {{
            throw IllegalStateException("Resource '$resourceId' locked by '${{current.owner}}'")
        }}
        val token = counters.computeIfAbsent(resourceId) {{ AtomicLong(0) }}.incrementAndGet()
        locks[resourceId] = LockEntry(owner, now.plusMillis(ttlMillis), token)
        return token
    }}

    @Synchronized
    fun release(resourceId: String, owner: String) {{
        val current = locks[resourceId]
        if (current != null && current.owner == owner) {{
            locks.remove(resourceId)
        }}
    }}

    fun isLocked(resourceId: String): Boolean {{
        val current = locks[resourceId]
        return current != null && current.expiresAt.isAfter(Instant.now())
    }}
}}
"""

    return files


def generate_php_domain_workflow_files(request: SynthesisRequest) -> Dict[str, str]:
    """Generate industrial-grade DDD, FSM, and Distributed Transaction files for PHP Laravel 11."""
    files: Dict[str, str] = {}
    entity = request.entities[0] if request.entities else None
    entity_name = pascal(entity.singular) if entity else "Order"

    # 1. Value Objects
    files["app/Domain/ValueObjects/Money.php"] = """<?php

namespace App\\Domain\\ValueObjects;

use InvalidArgumentException;

final readonly class Money
{
    public float $amount;
    public string $currency;

    public function __construct(float $amount, string $currency = 'USD')
    {
        if ($amount < 0) {
            throw new InvalidArgumentException("Amount cannot be negative: {$amount}");
        }
        $norm = strtoupper(trim($currency));
        if (!preg_match('/^[A-Z]{3}$/', $norm)) {
            throw new InvalidArgumentException("Invalid ISO-4217 currency: {$norm}");
        }
        $this->amount = $amount;
        $this->currency = $norm;
    }

    public function add(Money $other): Money
    {
        if ($this->currency !== $other->currency) {
            throw new InvalidArgumentException("Currency mismatch: {$this->currency} vs {$other->currency}");
        }
        return new Money($this->amount + $other->amount, $this->currency);
    }

    public function subtract(Money $other): Money
    {
        if ($this->currency !== $other->currency) {
            throw new InvalidArgumentException("Currency mismatch: {$this->currency} vs {$other->currency}");
        }
        if ($this->amount < $other->amount) {
            throw new InvalidArgumentException("Insufficient funds for subtraction");
        }
        return new Money($this->amount - $other->amount, $this->currency);
    }
}
"""

    files["app/Domain/ValueObjects/Address.php"] = """<?php

namespace App\\Domain\\ValueObjects;

final readonly class Address
{
    public function __construct(
        public string $street,
        public string $city,
        public string $stateProvince,
        public string $postalCode,
        public string $country = 'CN'
    ) {}
}
"""

    # 2. Aggregate Root
    files[f"app/Domain/Entities/{entity_name}Aggregate.php"] = f"""<?php

namespace App\\Domain\\Entities;

use App\\Domain\\ValueObjects\\Money;
use DateTimeImmutable;
use InvalidArgumentException;
use RuntimeException;

class {entity_name}Aggregate
{{
    public readonly string $id;
    public readonly string $tenantId;
    public string $reference;
    public Money $total;
    public string $status;
    public int $version;
    public readonly DateTimeImmutable $createdAt;
    public DateTimeImmutable $updatedAt;
    private array $uncommittedEvents = [];

    public function __construct(
        ?string $id,
        string $tenantId,
        string $reference,
        Money $total
    ) {{
        $this->id = $id ?? 'agg-' . substr(bin2hex(random_bytes(8)), 0, 12);
        $this->tenantId = $tenantId;
        $this->reference = $reference;
        $this->total = $total;
        $this->status = 'CREATED';
        $this->version = 1;
        $this->createdAt = new DateTimeImmutable();
        $this->updatedAt = new DateTimeImmutable();

        $this->validateInvariants();
        $this->recordEvent('{entity_name}Created', [
            'id' => $this->id,
            'reference' => $this->reference,
            'total' => $this->total->amount,
            'currency' => $this->total->currency,
        ]);
    }}

    public function updateDetails(string $newReference, Money $newTotal): void
    {{
        $this->reference = $newReference;
        $this->total = $newTotal;
        $this->version++;
        $this->updatedAt = new DateTimeImmutable();
        $this->validateInvariants();
        $this->recordEvent('{entity_name}Updated', [
            'id' => $this->id,
            'reference' => $this->reference,
            'total' => $this->total->amount,
        ]);
    }}

    public function transitionStatus(string $newStatus): void
    {{
        $this->status = $newStatus;
        $this->version++;
        $this->updatedAt = new DateTimeImmutable();
        $this->recordEvent('{entity_name}StatusTransitioned', [
            'id' => $this->id,
            'newStatus' => $newStatus,
        ]);
    }}

    private function validateInvariants(): void
    {{
        if (trim($this->reference) === '') {{
            throw new InvalidArgumentException("Domain Invariant Violation: Reference cannot be empty");
        }}
        if ($this->total->amount < 0) {{
            throw new InvalidArgumentException("Domain Invariant Violation: Total cannot be negative");
        }}
    }}

    private function recordEvent(string $eventType, array $payload): void
    {{
        $this->uncommittedEvents[] = [
            'eventId' => 'evt-' . substr(bin2hex(random_bytes(8)), 0, 16),
            'aggregateType' => '{entity_name}',
            'aggregateId' => $this->id,
            'eventType' => $eventType,
            'payload' => $payload,
            'occurredAt' => (new DateTimeImmutable())->format(DATE_ATOM),
        ];
    }}

    public function pollEvents(): array
    {{
        $events = $this->uncommittedEvents;
        $this->uncommittedEvents = [];
        return $events;
    }}
}}
"""

    # 3. Workflow State Machine (FSM)
    files[f"app/Workflow/{entity_name}StateMachine.php"] = f"""<?php

namespace App\\Workflow;

use App\\Domain\\Entities\\{entity_name}Aggregate;
use RuntimeException;

class {entity_name}StateMachine
{{
    private array $journal = [];

    private const TRANSITIONS = [
        'CREATED' => ['SUBMIT' => 'PENDING_PAYMENT', 'CANCEL' => 'CANCELLED'],
        'PENDING_PAYMENT' => ['PAY' => 'PAID', 'CANCEL' => 'CANCELLED'],
        'PAID' => ['COMPLETE' => 'FULFILLED', 'REFUND' => 'REFUNDED'],
    ];

    public function transition({entity_name}Aggregate $aggregate, string $trigger, string $operator): string
    {{
        $current = $aggregate->status;
        $allowed = self::TRANSITIONS[$current] ?? [];
        if (!isset($allowed[$trigger])) {{
            throw new RuntimeException("Invalid state transition from " . $current . " via " . $trigger);
        }}

        if ($trigger === 'PAY' && $aggregate->total->amount <= 0) {{
            throw new RuntimeException("Guard violation: Cannot pay zero or negative total");
        }}

        $next = $allowed[$trigger];
        $aggregate->transitionStatus($next);

        $this->journal[] = [
            'aggregateId' => $aggregate->id,
            'fromState' => $current,
            'toState' => $next,
            'trigger' => $trigger,
            'operator' => $operator,
            'transitionedAt' => date('c'),
        ];

        return $next;
    }}

    public function getJournal(): array
    {{
        return $this->journal;
    }}
}}
"""

    # 4. Distributed Transactions (Saga Orchestrator)
    files["app/Transactions/SagaOrchestrator.php"] = """<?php

namespace App\\Transactions;

use Throwable;

class SagaOrchestrator
{
    private array $steps = [];

    public function addStep(string $name, callable $forward, callable $compensation): self
    {
        $this->steps[] = ['name' => $name, 'forward' => $forward, 'compensation' => $compensation];
        return $this;
    }

    public function execute(): bool
    {
        $executed = [];
        foreach ($this->steps as $step) {
            try {
                $ok = ($step['forward'])();
                if (!$ok) {
                    $this->rollback($executed);
                    return false;
                }
                $executed[] = $step;
            } catch (Throwable $e) {
                $this->rollback($executed);
                return false;
            }
        }
        return true;
    }

    private function rollback(array $executed): void
    {
        while (!empty($executed)) {
            $step = array_pop($executed);
            try {
                ($step['compensation'])();
            } catch (Throwable) {
            }
        }
    }
}
"""

    # 5. Distributed Lock with Monotonic Fencing Token
    files["app/Transactions/DistributedLockManager.php"] = """<?php

namespace App\\Transactions;

use RuntimeException;

class DistributedLockManager
{
    private array $locks = [];
    private array $counters = [];

    public function acquire(string $resourceId, string $owner, int $ttlSeconds): int
    {
        $now = time();
        if (isset($this->locks[$resourceId])) {
            $current = $this->locks[$resourceId];
            if ($current['expiresAt'] > $now && $current['owner'] !== $owner) {
                throw new RuntimeException("Resource '{$resourceId}' is locked by '{$current['owner']}'");
            }
        }

        $this->counters[$resourceId] = ($this->counters[$resourceId] ?? 0) + 1;
        $token = $this->counters[$resourceId];

        $this->locks[$resourceId] = [
            'owner' => $owner,
            'expiresAt' => $now + $ttlSeconds,
            'fencingToken' => $token,
        ];

        return $token;
    }

    public function release(string $resourceId, string $owner): void
    {
        if (isset($this->locks[$resourceId]) && $this->locks[$resourceId]['owner'] === $owner) {
            unset($this->locks[$resourceId]);
        }
    }

    public function isLocked(string $resourceId): bool
    {
        return isset($this->locks[$resourceId]) && $this->locks[$resourceId]['expiresAt'] > time();
    }
}
"""

    return files
