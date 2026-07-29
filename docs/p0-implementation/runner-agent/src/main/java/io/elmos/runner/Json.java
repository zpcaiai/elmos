package io.elmos.runner;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Minimal JSON reader and writer.
 *
 * <p>The Runner Agent deliberately carries zero third-party dependencies: it runs
 * on every node, it handles untrusted customer workloads, and a single auditable
 * jar with no transitive tree is worth more here than the convenience of a full
 * databind library. The only JSON this class ever sees is the control-plane
 * protocol, which we define, so the surface is small and closed.</p>
 *
 * <p>Values map to {@code Map<String,Object>}, {@code List<Object>},
 * {@code String}, {@code Double}, {@code Boolean} and {@code null}.</p>
 */
public final class Json {

    private Json() {
    }

    public static final class JsonException extends RuntimeException {
        private static final long serialVersionUID = 1L;

        public JsonException(String message) {
            super(message);
        }
    }

    // ---- parsing -----------------------------------------------------------

    public static Object parse(String text) {
        Parser parser = new Parser(text);
        parser.skipWhitespace();
        Object value = parser.readValue(0);
        parser.skipWhitespace();
        if (!parser.atEnd()) {
            throw new JsonException("trailing content at " + parser.position);
        }
        return value;
    }

    @SuppressWarnings("unchecked")
    public static Map<String, Object> parseObject(String text) {
        Object value = parse(text);
        if (!(value instanceof Map)) {
            throw new JsonException("expected an object");
        }
        return (Map<String, Object>) value;
    }

    private static final class Parser {
        private static final int MAX_DEPTH = 64;
        private final String text;
        private int position;

        Parser(String text) {
            this.text = text == null ? "" : text;
        }

        boolean atEnd() {
            return position >= text.length();
        }

        void skipWhitespace() {
            while (position < text.length()) {
                char c = text.charAt(position);
                if (c == ' ' || c == '\t' || c == '\n' || c == '\r') {
                    position++;
                } else {
                    return;
                }
            }
        }

        Object readValue(int depth) {
            if (depth > MAX_DEPTH) {
                // A hostile or malformed payload must not blow the stack.
                throw new JsonException("nesting too deep");
            }
            skipWhitespace();
            if (atEnd()) {
                throw new JsonException("unexpected end of input");
            }
            char c = text.charAt(position);
            return switch (c) {
                case '{' -> readObject(depth);
                case '[' -> readArray(depth);
                case '"' -> readString();
                case 't' -> readLiteral("true", Boolean.TRUE);
                case 'f' -> readLiteral("false", Boolean.FALSE);
                case 'n' -> readLiteral("null", null);
                default -> readNumber();
            };
        }

        Map<String, Object> readObject(int depth) {
            expect('{');
            Map<String, Object> result = new LinkedHashMap<>();
            skipWhitespace();
            if (peek() == '}') {
                position++;
                return result;
            }
            while (true) {
                skipWhitespace();
                String key = readString();
                skipWhitespace();
                expect(':');
                Object value = readValue(depth + 1);
                result.put(key, value);
                skipWhitespace();
                char c = next();
                if (c == '}') {
                    return result;
                }
                if (c != ',') {
                    throw new JsonException("expected , or } at " + position);
                }
            }
        }

        List<Object> readArray(int depth) {
            expect('[');
            List<Object> result = new ArrayList<>();
            skipWhitespace();
            if (peek() == ']') {
                position++;
                return result;
            }
            while (true) {
                result.add(readValue(depth + 1));
                skipWhitespace();
                char c = next();
                if (c == ']') {
                    return result;
                }
                if (c != ',') {
                    throw new JsonException("expected , or ] at " + position);
                }
            }
        }

        String readString() {
            expect('"');
            StringBuilder builder = new StringBuilder();
            while (true) {
                if (atEnd()) {
                    throw new JsonException("unterminated string");
                }
                char c = text.charAt(position++);
                if (c == '"') {
                    return builder.toString();
                }
                if (c != '\\') {
                    builder.append(c);
                    continue;
                }
                if (atEnd()) {
                    throw new JsonException("unterminated escape");
                }
                char escape = text.charAt(position++);
                switch (escape) {
                    case '"' -> builder.append('"');
                    case '\\' -> builder.append('\\');
                    case '/' -> builder.append('/');
                    case 'b' -> builder.append('\b');
                    case 'f' -> builder.append('\f');
                    case 'n' -> builder.append('\n');
                    case 'r' -> builder.append('\r');
                    case 't' -> builder.append('\t');
                    case 'u' -> {
                        if (position + 4 > text.length()) {
                            throw new JsonException("truncated unicode escape");
                        }
                        builder.append((char) Integer.parseInt(text.substring(position, position + 4), 16));
                        position += 4;
                    }
                    default -> throw new JsonException("bad escape \\" + escape);
                }
            }
        }

        Object readLiteral(String literal, Object value) {
            if (!text.startsWith(literal, position)) {
                throw new JsonException("bad literal at " + position);
            }
            position += literal.length();
            return value;
        }

        Double readNumber() {
            int start = position;
            if (peek() == '-' || peek() == '+') {
                position++;
            }
            while (!atEnd()) {
                char c = text.charAt(position);
                if ((c >= '0' && c <= '9') || c == '.' || c == 'e' || c == 'E' || c == '-' || c == '+') {
                    position++;
                } else {
                    break;
                }
            }
            if (start == position) {
                throw new JsonException("expected a value at " + start);
            }
            try {
                return Double.valueOf(text.substring(start, position));
            } catch (NumberFormatException ex) {
                throw new JsonException("bad number at " + start);
            }
        }

        char peek() {
            return atEnd() ? '\0' : text.charAt(position);
        }

        char next() {
            if (atEnd()) {
                throw new JsonException("unexpected end of input");
            }
            return text.charAt(position++);
        }

        void expect(char expected) {
            char c = next();
            if (c != expected) {
                throw new JsonException("expected " + expected + " at " + (position - 1));
            }
        }
    }

    // ---- writing -----------------------------------------------------------

    public static String write(Object value) {
        StringBuilder builder = new StringBuilder();
        writeValue(builder, value, 0);
        return builder.toString();
    }

    private static void writeValue(StringBuilder out, Object value, int depth) {
        if (depth > 64) {
            throw new JsonException("nesting too deep");
        }
        if (value == null) {
            out.append("null");
        } else if (value instanceof String s) {
            writeString(out, s);
        } else if (value instanceof Boolean b) {
            out.append(b ? "true" : "false");
        } else if (value instanceof Integer || value instanceof Long || value instanceof Short) {
            out.append(value);
        } else if (value instanceof Number n) {
            double d = n.doubleValue();
            if (Double.isNaN(d) || Double.isInfinite(d)) {
                throw new JsonException("non-finite number");
            }
            if (d == Math.rint(d) && Math.abs(d) < 1e15) {
                out.append((long) d);
            } else {
                out.append(d);
            }
        } else if (value instanceof Map<?, ?> map) {
            out.append('{');
            boolean first = true;
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                if (!first) {
                    out.append(',');
                }
                first = false;
                writeString(out, String.valueOf(entry.getKey()));
                out.append(':');
                writeValue(out, entry.getValue(), depth + 1);
            }
            out.append('}');
        } else if (value instanceof Iterable<?> items) {
            out.append('[');
            boolean first = true;
            for (Object item : items) {
                if (!first) {
                    out.append(',');
                }
                first = false;
                writeValue(out, item, depth + 1);
            }
            out.append(']');
        } else {
            writeString(out, String.valueOf(value));
        }
    }

    private static void writeString(StringBuilder out, String value) {
        out.append('"');
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\b' -> out.append("\\b");
                case '\f' -> out.append("\\f");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (c < 0x20) {
                        out.append(String.format("\\u%04x", (int) c));
                    } else {
                        out.append(c);
                    }
                }
            }
        }
        out.append('"');
    }

    // ---- typed accessors ---------------------------------------------------

    public static String string(Map<String, Object> source, String key, String fallback) {
        Object value = source.get(key);
        return value instanceof String s ? s : fallback;
    }

    public static boolean bool(Map<String, Object> source, String key, boolean fallback) {
        Object value = source.get(key);
        return value instanceof Boolean b ? b : fallback;
    }

    public static int integer(Map<String, Object> source, String key, int fallback) {
        Object value = source.get(key);
        return value instanceof Number n ? n.intValue() : fallback;
    }

    @SuppressWarnings("unchecked")
    public static List<Map<String, Object>> objects(Map<String, Object> source, String key) {
        Object value = source.get(key);
        List<Map<String, Object>> result = new ArrayList<>();
        if (value instanceof List<?> items) {
            for (Object item : items) {
                if (item instanceof Map) {
                    result.add((Map<String, Object>) item);
                }
            }
        }
        return result;
    }

    @SuppressWarnings("unchecked")
    public static Map<String, Object> object(Map<String, Object> source, String key) {
        Object value = source.get(key);
        return value instanceof Map ? (Map<String, Object>) value : Map.of();
    }
}
