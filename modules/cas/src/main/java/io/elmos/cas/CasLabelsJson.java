package io.elmos.cas;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;

/** Dependency-free codec for the catalog's constrained {@code jsonb<string,string>} labels. */
final class CasLabelsJson {

    private CasLabelsJson() {
    }

    static String encode(Map<String, String> labels) {
        Objects.requireNonNull(labels, "labels");
        labels.forEach((key, value) -> {
            CasText.withoutNul(key, "label key");
            CasText.withoutNul(value, "label value");
        });
        StringBuilder json = new StringBuilder("{");
        boolean first = true;
        for (Map.Entry<String, String> label : new TreeMap<>(labels).entrySet()) {
            if (!first) {
                json.append(',');
            }
            first = false;
            json.append(CasManifest.CanonicalEncoder.jsonString(label.getKey())).append(':')
                    .append(CasManifest.CanonicalEncoder.jsonString(label.getValue()));
        }
        return json.append('}').toString();
    }

    static Map<String, String> decode(String json) {
        return new Parser(Objects.requireNonNull(json, "json")).parse();
    }

    private static final class Parser {
        private final String input;
        private int offset;

        private Parser(String input) {
            this.input = input;
        }

        private Map<String, String> parse() {
            skipWhitespace();
            expect('{');
            skipWhitespace();
            Map<String, String> labels = new LinkedHashMap<>();
            if (consume('}')) {
                requireEnd();
                return Map.of();
            }
            while (true) {
                String key = string();
                CasText.withoutNul(key, "label key");
                skipWhitespace();
                expect(':');
                skipWhitespace();
                String value = string();
                CasText.withoutNul(value, "label value");
                if (labels.putIfAbsent(key, value) != null) {
                    throw invalid("duplicate label key");
                }
                skipWhitespace();
                if (consume('}')) {
                    requireEnd();
                    return Map.copyOf(new TreeMap<>(labels));
                }
                expect(',');
                skipWhitespace();
            }
        }

        private String string() {
            expect('"');
            StringBuilder value = new StringBuilder();
            while (offset < input.length()) {
                char current = input.charAt(offset++);
                if (current == '"') {
                    return value.toString();
                }
                if (current == '\\') {
                    if (offset >= input.length()) {
                        throw invalid("unterminated escape");
                    }
                    char escaped = input.charAt(offset++);
                    switch (escaped) {
                        case '"', '\\', '/' -> value.append(escaped);
                        case 'b' -> value.append('\b');
                        case 'f' -> value.append('\f');
                        case 'n' -> value.append('\n');
                        case 'r' -> value.append('\r');
                        case 't' -> value.append('\t');
                        case 'u' -> value.append(unicodeEscape());
                        default -> throw invalid("unsupported escape");
                    }
                } else {
                    if (current < 0x20) {
                        throw invalid("unescaped control character");
                    }
                    value.append(current);
                }
            }
            throw invalid("unterminated string");
        }

        private char unicodeEscape() {
            if (offset + 4 > input.length()) {
                throw invalid("short unicode escape");
            }
            int value = 0;
            for (int index = 0; index < 4; index++) {
                int digit = Character.digit(input.charAt(offset++), 16);
                if (digit < 0) {
                    throw invalid("invalid unicode escape");
                }
                value = (value << 4) | digit;
            }
            return (char) value;
        }

        private void expect(char expected) {
            if (!consume(expected)) {
                throw invalid("expected '" + expected + "'");
            }
        }

        private boolean consume(char expected) {
            if (offset < input.length() && input.charAt(offset) == expected) {
                offset++;
                return true;
            }
            return false;
        }

        private void skipWhitespace() {
            while (offset < input.length() && Character.isWhitespace(input.charAt(offset))) {
                offset++;
            }
        }

        private void requireEnd() {
            skipWhitespace();
            if (offset != input.length()) {
                throw invalid("trailing content");
            }
        }

        private IllegalArgumentException invalid(String detail) {
            return new IllegalArgumentException("invalid catalog labels JSON at offset " + offset + ": " + detail);
        }
    }
}
