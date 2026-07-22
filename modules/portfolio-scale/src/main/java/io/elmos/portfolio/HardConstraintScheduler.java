package io.elmos.portfolio;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import static io.elmos.portfolio.PortfolioScaleModels.*;

public final class HardConstraintScheduler {
    public SchedulingResult scheduleWave(List<WorkUnit> workUnits, List<Runner> runners) {
        Set<String> occupied = new HashSet<>();
        List<Assignment> assignments = new ArrayList<>();
        List<String> unscheduled = new ArrayList<>();
        for (WorkUnit unit : workUnits) {
            Runner selected = runners.stream()
                    .filter(runner -> !occupied.contains(runner.id()))
                    .filter(runner -> runner.attested())
                    .filter(runner -> runner.tenantId().equals(unit.tenantId()))
                    .filter(runner -> unit.regions().contains(runner.region()))
                    .filter(runner -> runner.toolchains().contains(unit.toolchain()))
                    .filter(runner -> runner.maximumLoc() >= unit.estimatedLoc())
                    .sorted(Comparator.comparing(Runner::id)).findFirst().orElse(null);
            if (selected == null) {
                unscheduled.add(unit.id());
            } else {
                occupied.add(selected.id());
                assignments.add(new Assignment(unit.id(), selected.id()));
            }
        }
        return new SchedulingResult(assignments, unscheduled);
    }
}
