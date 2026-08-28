package io.elmos.workflow;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import org.junit.jupiter.api.Test;

class TaskFinopsQualificationGateTest {
    @Test
    void missingRuntimeCheckBlocksLocalGate() {
        TaskFinopsQualificationGate.GateResult result =
                TaskFinopsQualificationGate.evaluate(
                        new TaskFinopsQualificationGate.GateRequest(
                                List.of(new TaskFinopsQualificationGate.Check(
                                        "temporal-replay", TaskFinopsQualificationGate.CheckStatus.NOT_RUN,
                                        "provider runtime was not executed")),
                                "NOT_RUN", "NOT_CERTIFIED"));

        assertEquals(TaskFinopsQualificationGate.Decision.BLOCKED, result.decision());
        assertEquals("NOT_RUN", result.externalEvidenceStatus());
        assertEquals("NOT_CERTIFIED", result.productionCertification());
    }

    @Test
    void passingLocalChecksOnlyPrepareExternalGate() {
        TaskFinopsQualificationGate.GateResult result =
                TaskFinopsQualificationGate.evaluate(
                        new TaskFinopsQualificationGate.GateRequest(
                                List.of(new TaskFinopsQualificationGate.Check(
                                        "static-contracts", TaskFinopsQualificationGate.CheckStatus.PASS,
                                        "pure contract checks passed")),
                                "NOT_RUN", "NOT_CERTIFIED"));

        assertEquals(TaskFinopsQualificationGate.Decision.READY_FOR_EXTERNAL_GATE,
                result.decision());
        assertEquals("NOT_RUN", result.externalEvidenceStatus());
        assertEquals("NOT_CERTIFIED", result.productionCertification());
    }
}
