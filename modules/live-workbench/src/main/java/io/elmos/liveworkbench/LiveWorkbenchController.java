package io.elmos.liveworkbench;

import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.util.List;
import java.util.Map;

import static io.elmos.liveworkbench.ProductionContracts.*;

@RestController
@RequestMapping("/api/v1/live-workbench")
public final class LiveWorkbenchController {
    public record ReadyEnvelope(long expectedVersion, ReadinessRequest readiness) {}
    public record DebugEnvelope(int generation, DebugRequest command) {}
    public record TerminateEnvelope(long expectedVersion, String reason) {}

    private final ProductionLiveWorkbenchService workbench;
    private final PrincipalScopeResolver scopes;
    private final PreviewEventStreamRegistry streams;

    public LiveWorkbenchController(ProductionLiveWorkbenchService workbench, PrincipalScopeResolver scopes,
                                   PreviewEventStreamRegistry streams) {
        this.workbench = workbench; this.scopes = scopes; this.streams = streams;
    }

    @PostMapping("/sessions")
    public ApiSession create(Authentication authentication, @RequestHeader("Idempotency-Key") String idempotencyKey,
                             @RequestBody CreateSessionRequest request) {
        return workbench.create(scopes.resolve(authentication), request, idempotencyKey);
    }

    @GetMapping("/sessions/{sessionId}")
    public ApiSession status(Authentication authentication, @PathVariable String sessionId) {
        return workbench.status(scopes.resolve(authentication), sessionId);
    }

    @GetMapping("/sessions/{sessionId}/preview-access")
    public PreviewAccess previewAccess(Authentication authentication, @PathVariable String sessionId) {
        return workbench.previewAccess(scopes.resolve(authentication), sessionId);
    }

    @PostMapping("/sessions/{sessionId}/readiness")
    public ApiSession ready(Authentication authentication, @PathVariable String sessionId,
                            @RequestBody ReadyEnvelope envelope) {
        return workbench.markReady(scopes.resolve(authentication), sessionId, envelope.expectedVersion(), envelope.readiness());
    }

    @PostMapping("/sessions/{sessionId}/debug-commands")
    public DebugReceipt debug(Authentication authentication, @PathVariable String sessionId,
                              @RequestHeader("Idempotency-Key") String idempotencyKey,
                              @RequestBody DebugEnvelope envelope) {
        return workbench.debug(scopes.resolve(authentication), sessionId, envelope.generation(), envelope.command(), idempotencyKey);
    }

    @PostMapping("/sessions/{sessionId}/events")
    public EventView appendEvent(Authentication authentication, @PathVariable String sessionId,
                                 @RequestBody RuntimeEventRequest request) {
        var scope = scopes.resolve(authentication);
        EventView event = workbench.appendRuntimeEvent(scope, sessionId, request);
        streams.publish(scope.tenantId(), event);
        return event;
    }

    @GetMapping("/sessions/{sessionId}/events")
    public List<EventView> events(Authentication authentication, @PathVariable String sessionId,
                                  @RequestParam(defaultValue = "0") long after,
                                  @RequestParam(defaultValue = "100") int limit) {
        return workbench.events(scopes.resolve(authentication), sessionId, after, limit);
    }

    @GetMapping(path = "/sessions/{sessionId}/events/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter stream(Authentication authentication, @PathVariable String sessionId,
                             @RequestParam(defaultValue = "0") long after) throws IOException {
        var scope = scopes.resolve(authentication);
        List<EventView> replay = workbench.events(scope, sessionId, after, 500);
        SseEmitter emitter = streams.open(scope.tenantId(), sessionId);
        for (EventView event : replay)
            emitter.send(SseEmitter.event().id(Long.toString(event.sequence())).name(event.kind()).data(event));
        emitter.send(SseEmitter.event().name("cursor").data(Map.of("after", replay.isEmpty() ? after : replay.getLast().sequence())));
        return emitter;
    }

    @PostMapping("/sessions/{sessionId}/terminate")
    public ApiSession terminate(Authentication authentication, @PathVariable String sessionId,
                                @RequestBody TerminateEnvelope envelope) {
        var scope = scopes.resolve(authentication);
        ApiSession result = workbench.terminate(scope, sessionId, envelope.expectedVersion(), envelope.reason());
        streams.close(scope.tenantId(), sessionId);
        return result;
    }
}
