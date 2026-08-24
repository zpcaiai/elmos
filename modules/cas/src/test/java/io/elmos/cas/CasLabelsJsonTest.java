package io.elmos.cas;

import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CasLabelsJsonTest {

    @Test
    void arbitraryStringLabelsRoundTripWithoutLoss() {
        Map<String, String> labels = Map.of(
                "quote\"slash\\", "line one\nline two\t\u0001",
                "unicode", "\u4ed3\u5e93/\ud83d\ude80");

        assertEquals(labels, CasLabelsJson.decode(CasLabelsJson.encode(labels)));
    }

    @Test
    void postgresStyleWhitespaceAndUnicodeEscapesAreReadExactly() {
        assertEquals(Map.of("a", "one", "z", "\u4ed3"),
                CasLabelsJson.decode(" { \"z\" : \"\\u4ed3\", \"a\" : \"one\" } "));
    }

    @Test
    void malformedOrDuplicateLabelsFailClosed() {
        assertThrows(IllegalArgumentException.class,
                () -> CasLabelsJson.decode("{\"a\":\"one\",\"a\":\"two\"}"));
        assertThrows(IllegalArgumentException.class,
                () -> CasLabelsJson.decode("{\"a\":null}"));
        assertThrows(IllegalArgumentException.class,
                () -> CasLabelsJson.decode("{\"a\":\"unterminated}"));
        assertThrows(IllegalArgumentException.class,
                () -> CasLabelsJson.encode(Map.of("tenant", "a\0b")));
        assertThrows(IllegalArgumentException.class,
                () -> CasLabelsJson.decode("{\"tenant\":\"\\u0000\"}"));
    }
}
