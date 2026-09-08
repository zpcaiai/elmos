package io.elmos.liveworkbench;

import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

import static io.elmos.liveworkbench.LwContracts.CLEANUP_SECONDS;
import static io.elmos.liveworkbench.LwContracts.PREVIEW_SECONDS;
import static io.elmos.liveworkbench.ProductionContracts.EventView;

/** Ephemeral connection registry; event truth remains in PostgreSQL and is replayed by cursor. */
@Component
public final class PreviewEventStreamRegistry {
    private final ConcurrentHashMap<String, Set<SseEmitter>> emitters = new ConcurrentHashMap<>();

    public SseEmitter open(String tenantId, String sessionId) {
        SseEmitter emitter = new SseEmitter((PREVIEW_SECONDS + CLEANUP_SECONDS) * 1_000L);
        String key = key(tenantId, sessionId);
        emitters.computeIfAbsent(key, ignored -> ConcurrentHashMap.newKeySet()).add(emitter);
        Runnable remove = () -> remove(key, emitter);
        emitter.onCompletion(remove); emitter.onTimeout(remove); emitter.onError(error -> remove.run());
        return emitter;
    }

    public void publish(String tenantId, EventView event) {
        String key = key(tenantId, event.sessionId());
        for (SseEmitter emitter : emitters.getOrDefault(key, Set.of())) {
            try {
                emitter.send(SseEmitter.event().id(Long.toString(event.sequence())).name(event.kind()).data(event));
            } catch (IOException | IllegalStateException error) {
                remove(key, emitter);
            }
        }
    }

    public void close(String tenantId, String sessionId) {
        Set<SseEmitter> removed = emitters.remove(key(tenantId, sessionId));
        if (removed != null) removed.forEach(SseEmitter::complete);
    }

    private void remove(String key, SseEmitter emitter) {
        Set<SseEmitter> values = emitters.get(key);
        if (values != null) {
            values.remove(emitter);
            if (values.isEmpty()) emitters.remove(key, values);
        }
    }
    private static String key(String tenantId, String sessionId) { return tenantId + "\u0000" + sessionId; }
}
