package io.elmos.liveworkbench;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static io.elmos.liveworkbench.LwContracts.*;

/** Fenced command ledger: retrying an unknown side effect is intentionally impossible. */
public final class DebugCommandLedger {
    public record Result(CommandState state, String code, String evidenceId) {}
    private record Entry(DebugCommand command, CommandState state, String evidenceId) {}
    private final Map<String, Entry> commands = new HashMap<>();
    private final Map<String, Long> lastSequence = new HashMap<>();
    private final List<RuntimeEvent> events = new ArrayList<>();

    public synchronized Result submit(Authority authority, PreviewSession session, DebugCommand command, long now, boolean adapterAcknowledged) {
        if (!authority.validAt(now, command.requiredCapability()) || !session.binding().equals(command.binding()) || !authority.binding().equals(command.binding()))
            return new Result(CommandState.DENIED, "DEBUG_AUTHORITY_DENIED", null);
        if (!session.liveAt(now) || command.deadline() != session.expiresAt() || command.binding().generation() != session.binding().generation())
            return new Result(CommandState.DENIED, "DEBUG_SESSION_FENCED_OR_EXPIRED", null);
        String key = command.binding().tenantId()+"|"+command.binding().sessionId()+"|"+command.idempotencyKey();
        Entry prior = commands.get(key);
        if (prior != null) {
            if (!samePayload(prior.command(), command)) return new Result(CommandState.DENIED, "IDEMPOTENCY_PAYLOAD_CONFLICT", null);
            return new Result(prior.state(), prior.state() == CommandState.UNKNOWN ? "RECONCILE_BEFORE_RETRY" : "IDEMPOTENT_REPLAY", prior.evidenceId());
        }
        CommandState state = adapterAcknowledged ? CommandState.COMMITTED : CommandState.UNKNOWN;
        String evidence = adapterAcknowledged ? "debug-command:"+command.commandId() : null;
        commands.put(key, new Entry(command, state, evidence));
        return new Result(state, adapterAcknowledged ? "DEBUG_COMMAND_COMMITTED" : "DEBUG_COMMAND_UNKNOWN_RECONCILIATION_REQUIRED", evidence);
    }

    public synchronized void appendCommitted(RuntimeEvent event) {
        String key = event.binding().tenantId()+"|"+event.binding().sessionId()+"|"+event.binding().generation();
        long previous = lastSequence.getOrDefault(key, 0L);
        if (event.sequence() <= previous) throw new IllegalArgumentException("non-monotonic event sequence");
        lastSequence.put(key, event.sequence()); events.add(event);
    }
    public synchronized List<RuntimeEvent> resume(Authority authority, long afterSequence, long now) {
        if (!authority.validAt(now, Capability.INSPECT)) throw new SecurityException("inspect authority required");
        return events.stream().filter(e -> e.binding().equals(authority.binding()) && e.sequence() > afterSequence).toList();
    }
    private static boolean samePayload(DebugCommand left, DebugCommand right) {
        return left.binding().equals(right.binding()) && left.command().equals(right.command()) && left.argumentsDigest().equals(right.argumentsDigest()) && left.stopEpoch() == right.stopEpoch();
    }
}
