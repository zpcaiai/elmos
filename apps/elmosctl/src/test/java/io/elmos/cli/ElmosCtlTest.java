package io.elmos.cli;

import org.junit.jupiter.api.Test;

import java.io.ByteArrayOutputStream;
import java.io.PrintStream;

import static org.junit.jupiter.api.Assertions.*;

class ElmosCtlTest {
    @Test void mutationRequiresExplicitEvidenceAndConfirmation() {
        var out = new ByteArrayOutputStream(); var error = new ByteArrayOutputStream();
        assertEquals(3, ElmosCtl.run(new String[]{"install"}, new PrintStream(out), new PrintStream(error)));
        assertTrue(error.toString().contains("APPROVED_EVIDENCE_AND_CONFIRMATION_REQUIRED"));
        assertEquals(0, ElmosCtl.run(new String[]{"install", "--evidence-approved", "--confirm"},
                new PrintStream(out), new PrintStream(error)));
    }
    @Test void verificationWithoutTargetIsExplicitlyNotRun() {
        var out = new ByteArrayOutputStream();
        assertEquals(4, ElmosCtl.run(new String[]{"verify"}, new PrintStream(out), System.err));
        assertTrue(out.toString().contains("NOT_RUN"));
    }
}
