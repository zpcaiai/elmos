package io.elmos.liveworkbench;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public final class LiveWorkbenchReaper {
    private final ProductionLiveWorkbenchService service;
    public LiveWorkbenchReaper(ProductionLiveWorkbenchService service) { this.service = service; }

    @Scheduled(fixedDelayString = "${elmos.live-workbench.reaper-delay-ms:5000}")
    public void reap() { service.sweepExpired(100); }
}
