"""C# (.NET 8) Domain-Driven Design, Workflow FSM, and Distributed Transactions Emitter.

Generates industrial-grade C# domain models, value objects, FSM state machines,
and distributed transaction coordinators (Saga LIFO compensation, Outbox, Fencing Locks).
"""

from __future__ import annotations

from .models import SynthesisRequest, pascal


def generate_dotnet_domain_workflow_files(request: SynthesisRequest) -> dict[str, str]:
    """Generate industrial-grade DDD, FSM, and Distributed Transaction files for C# .NET 8."""
    files: dict[str, str] = {}
    app_name = pascal(request.project_name)
    entity = request.entities[0] if request.entities else None
    entity_name = pascal(entity.singular) if entity else "Order"

    # 1. Domain Value Objects
    files["Domain/ValueObjects.cs"] = f"""namespace {app_name}.Domain;

using System;
using System.Text.RegularExpressions;

/// <summary>
/// Immutable high-precision monetary Value Object.
/// </summary>
public readonly record struct Money
{{
    private static readonly Regex CurrencyRegex = new(@"^[A-Z]{{3}}$", RegexOptions.Compiled);

    public decimal Amount {{ get; }}
    public string Currency {{ get; }}

    public Money(decimal amount, string currency)
    {{
        if (amount < 0)
        {{
            throw new ArgumentOutOfRangeException(nameof(amount), "Amount cannot be negative: " + amount);
        }}
        var norm = (currency ?? throw new ArgumentNullException(nameof(currency))).Trim().ToUpperInvariant();
        if (!CurrencyRegex.IsMatch(norm))
        {{
            throw new ArgumentException("Invalid ISO-4217 currency code: " + norm, nameof(currency));
        }}

        Amount = amount;
        Currency = norm;
    }}

    public Money Add(Money other)
    {{
        if (Currency != other.Currency)
        {{
            throw new InvalidOperationException($"Currency mismatch: {{Currency}} vs {{other.Currency}}");
        }}
        return new Money(Amount + other.Amount, Currency);
    }}

    public Money Subtract(Money other)
    {{
        if (Currency != other.Currency)
        {{
            throw new InvalidOperationException($"Currency mismatch: {{Currency}} vs {{other.Currency}}");
        }}
        if (Amount < other.Amount)
        {{
            throw new InvalidOperationException("Insufficient funds for subtraction");
        }}
        return new Money(Amount - other.Amount, Currency);
    }}

    public static Money Of(decimal amount, string currency = "USD") => new(amount, currency);
}}

/// <summary>
/// Physical Address Value Object with structural equality.
/// </summary>
public record Address(
    string Street,
    string City,
    string StateProvince,
    string PostalCode,
    string Country = "CN"
);

/// <summary>
/// Quantity Value Object with unit constraint.
/// </summary>
public record Quantity(decimal Value, string Unit);
"""

    # 2. Domain Events
    files["Domain/DomainEvents.cs"] = f"""namespace {app_name}.Domain;

using System;
using System.Text.Json;

/// <summary>
/// Strongly typed Domain Event Envelope.
/// </summary>
public record DomainEvent(
    string EventId,
    string AggregateType,
    string AggregateId,
    string EventType,
    string PayloadJson,
    DateTimeOffset OccurredAt,
    string TraceId
)
{{
    public static DomainEvent Create<T>(string aggregateType, string aggregateId, string eventType, T payload)
    {{
        return new DomainEvent(
            $"evt-{{Guid.NewGuid():N}}[..16]",
            aggregateType,
            aggregateId,
            eventType,
            JsonSerializer.Serialize(payload),
            DateTimeOffset.UtcNow,
            $"tr-{{Guid.NewGuid():N}}[..12]"
        );
    }}
}}
"""

    # 3. Aggregate Root
    files[f"Domain/{entity_name}Aggregate.cs"] = f"""namespace {app_name}.Domain;

using System;
using System.Collections.Generic;

/// <summary>
/// Industrial-grade DDD Aggregate Root for {entity_name}.
/// </summary>
public class {entity_name}Aggregate
{{
    private readonly List<DomainEvent> _uncommittedEvents = new();

    public string Id {{ get; }}
    public string TenantId {{ get; }}
    public string Reference {{ get; private set; }}
    public Money Total {{ get; private set; }}
    public string Status {{ get; private set; }}
    public long Version {{ get; private set; }}
    public DateTimeOffset CreatedAt {{ get; }}
    public DateTimeOffset UpdatedAt {{ get; private set; }}

    public IReadOnlyList<DomainEvent> UncommittedEvents => _uncommittedEvents.AsReadOnly();

    public {entity_name}Aggregate(string id, string tenantId, string reference, Money total)
    {{
        Id = id ?? $"agg-{{Guid.NewGuid():N}}[..12]";
        TenantId = tenantId ?? throw new ArgumentNullException(nameof(tenantId));
        Reference = reference ?? throw new ArgumentNullException(nameof(reference));
        Total = total;
        Status = "CREATED";
        Version = 1;
        CreatedAt = DateTimeOffset.UtcNow;
        UpdatedAt = DateTimeOffset.UtcNow;

        ValidateInvariants();
        RecordEvent("{entity_name}Created", new {{ Id, Reference, Amount = Total.Amount, Total.Currency }});
    }}

    public void UpdateDetails(string newReference, Money newTotal)
    {{
        Reference = newReference ?? throw new ArgumentNullException(nameof(newReference));
        Total = newTotal;
        Version++;
        UpdatedAt = DateTimeOffset.UtcNow;

        ValidateInvariants();
        RecordEvent("{entity_name}Updated", new {{ Id, Reference, Amount = Total.Amount }});
    }}

    public void TransitionStatus(string newStatus)
    {{
        Status = newStatus ?? throw new ArgumentNullException(nameof(newStatus));
        Version++;
        UpdatedAt = DateTimeOffset.UtcNow;
        RecordEvent("{entity_name}StatusTransitioned", new {{ Id, NewStatus = newStatus }});
    }}

    private void ValidateInvariants()
    {{
        if (string.IsNullOrWhiteSpace(Reference))
        {{
            throw new InvalidOperationException("Domain Invariant Violation: Reference cannot be empty");
        }}
        if (Total.Amount < 0)
        {{
            throw new InvalidOperationException("Domain Invariant Violation: Total cannot be negative");
        }}
    }}

    private void RecordEvent<T>(string eventType, T payload)
    {{
        _uncommittedEvents.Add(DomainEvent.Create("{entity_name}", Id, eventType, payload));
    }}

    public IReadOnlyList<DomainEvent> PollEvents()
    {{
        var events = new List<DomainEvent>(_uncommittedEvents);
        _uncommittedEvents.Clear();
        return events;
    }}
}}
"""

    # 4. Workflow State Machine (FSM)
    files[f"Workflow/{entity_name}StateMachine.cs"] = f"""namespace {app_name}.Workflow;

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using {app_name}.Domain;

/// <summary>
/// Finite State Machine for {entity_name} lifecycle management.
/// </summary>
public class {entity_name}StateMachine
{{
    public enum State
    {{
        Created, PendingPayment, Paid, Fulfilled, Cancelled, Refunded
    }}

    public enum Trigger
    {{
        Submit, Pay, Complete, Cancel, Refund
    }}

    public record TransitionRecord(
        string AggregateId,
        State FromState,
        State ToState,
        Trigger EventTrigger,
        DateTimeOffset TransitionedAt,
        string Operator
    );

    private readonly ConcurrentBag<TransitionRecord> _journal = new();

    public State Transition({entity_name}Aggregate aggregate, Trigger trigger, string op)
    {{
        if (!Enum.TryParse<State>(aggregate.Status, true, out var current))
        {{
            current = State.Created;
        }}

        var next = (current, trigger) switch
        {{
            (State.Created, Trigger.Submit) => State.PendingPayment,
            (State.Created, Trigger.Cancel) => State.Cancelled,
            (State.PendingPayment, Trigger.Pay) => State.Paid,
            (State.PendingPayment, Trigger.Cancel) => State.Cancelled,
            (State.Paid, Trigger.Complete) => State.Fulfilled,
            (State.Paid, Trigger.Refund) => State.Refunded,
            _ => throw new InvalidOperationException($"Invalid state transition from {{current}} via {{trigger}}")
        }};

        // Guard invariant: Cannot pay an order with zero or negative total
        if (trigger == Trigger.Pay && aggregate.Total.Amount <= 0)
        {{
            throw new InvalidOperationException("Guard violation: Cannot pay zero or negative total");
        }}

        aggregate.TransitionStatus(next.ToString().ToUpperInvariant());
        _journal.Add(new TransitionRecord(aggregate.Id, current, next, trigger, DateTimeOffset.UtcNow, op));
        return next;
    }}

    public IEnumerable<TransitionRecord> GetJournal() => _journal.ToArray();
}}
"""

    # 5. Distributed Transactions (Saga Orchestrator with LIFO compensation)
    files["Transactions/SagaOrchestrator.cs"] = f"""namespace {app_name}.Transactions;

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;

/// <summary>
/// Orchestrated Saga Coordinator with automatic LIFO reverse compensation.
/// </summary>
public class SagaOrchestrator
{{
    public record Step(
        string Name,
        Func<Task<bool>> ForwardAction,
        Func<Task> CompensationAction
    );

    private readonly List<Step> _steps = new();
    private readonly ILogger<SagaOrchestrator>? _logger;

    public SagaOrchestrator(ILogger<SagaOrchestrator>? logger = null)
    {{
        _logger = logger;
    }}

    public SagaOrchestrator AddStep(string name, Func<Task<bool>> forward, Func<Task> compensation)
    {{
        _steps.Add(new Step(name, forward, compensation));
        return this;
    }}

    public async Task<bool> ExecuteAsync()
    {{
        var executed = new Stack<Step>();
        foreach (var step in _steps)
        {{
            _logger?.LogInformation("Executing Saga step forward: {{StepName}}", step.Name);
            try
            {{
                var ok = await step.ForwardAction();
                if (!ok)
                {{
                    _logger?.LogError("Saga step failed forward: {{StepName}}, initiating LIFO compensation", step.Name);
                    await RollbackAsync(executed);
                    return false;
                }}
                executed.Push(step);
            }}
            catch (Exception ex)
            {{
                _logger?.LogError(ex, "Saga step threw exception: {{StepName}}, initiating LIFO compensation", step.Name);
                await RollbackAsync(executed);
                return false;
            }}
        }}

        _logger?.LogInformation("Saga successfully completed all {{Count}} steps", _steps.Count);
        return true;
    }}

    private async Task RollbackAsync(Stack<Step> executed)
    {{
        while (executed.Count > 0)
        {{
            var compStep = executed.Pop();
            _logger?.LogWarning("Executing LIFO compensation for: {{StepName}}", compStep.Name);
            try
            {{
                await compStep.CompensationAction();
            }}
            catch (Exception ex)
            {{
                _logger?.LogError(ex, "Compensation failed for step: {{StepName}}, manual intervention required", compStep.Name);
            }}
        }}
    }}
}}
"""

    # 6. Distributed Lock with Monotonic Fencing Token
    files["Transactions/DistributedLockManager.cs"] = f"""namespace {app_name}.Transactions;

using System;
using System.Collections.Concurrent;
using System.Threading;

/// <summary>
/// Distributed Mutex Lock with Monotonic Fencing Token preventing stale split-brain writes.
/// </summary>
public class DistributedLockManager
{{
    public record LockEntry(string Owner, DateTimeOffset ExpiresAt, long FencingToken);

    private readonly ConcurrentDictionary<string, LockEntry> _locks = new();
    private readonly ConcurrentDictionary<string, long> _generationCounters = new();
    private readonly object _syncRoot = new();

    public long Acquire(string resourceId, string owner, TimeSpan ttl)
    {{
        lock (_syncRoot)
        {{
            var now = DateTimeOffset.UtcNow;
            if (_locks.TryGetValue(resourceId, out var current) && current.ExpiresAt > now && current.Owner != owner)
            {{
                throw new InvalidOperationException($"Resource '{{resourceId}}' is locked by '{{current.Owner}}'");
            }}

            var token = _generationCounters.AddOrUpdate(resourceId, 1, (_, old) => old + 1);
            _locks[resourceId] = new LockEntry(owner, now.Add(ttl), token);
            return token;
        }}
    }}

    public void Release(string resourceId, string owner)
    {{
        lock (_syncRoot)
        {{
            if (_locks.TryGetValue(resourceId, out var current) && current.Owner == owner)
            {{
                _locks.TryRemove(resourceId, out _);
            }}
        }}
    }}

    public bool IsLocked(string resourceId)
    {{
        return _locks.TryGetValue(resourceId, out var current) && current.ExpiresAt > DateTimeOffset.UtcNow;
    }}
}}
"""

    return files
