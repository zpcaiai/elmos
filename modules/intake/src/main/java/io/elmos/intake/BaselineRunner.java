package io.elmos.intake;

import static io.elmos.intake.IntakeModels.*;

/** Implementations must run only in an approved isolated workspace and return artifact references, never raw secrets. */
@FunctionalInterface
public interface BaselineRunner {
    BaselineReport run(RepositorySnapshot snapshot, BuildModel buildModel, SandboxPolicy sandboxPolicy);

    static BaselineRunner disabled(String reason) {
        return (snapshot, buildModel, policy) -> BaselineReport.notRun(snapshot.snapshotId(), reason);
    }
}
