package io.elmos.cas;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.TreeMap;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.LongSupplier;

/**
 * OpenTelemetry instrumentation for the CAS, expressed as a port plus an in-process
 * implementation, with an OTLP/HTTP exporter in {@link OtlpExporter}.
 *
 * <p>Why a port and not the OTel SDK: this module has a hard no-dependencies rule, and the SDK
 * plus its API, context and exporter artifacts is a large tree to take on for a library that is
 * meant to be embeddable. What is <em>not</em> reinvented is the data model — span and metric
 * shapes, attribute naming, and the wire payload follow the OTel spec, so a deployment that
 * already runs a collector points this at it and everything lands in the same place.
 *
 * <p>Attribute names follow the convention of `cas.*` for this component's own dimensions and
 * `elmos.*` for platform identifiers. Digests are recorded, tenant ids are recorded, and content
 * never is.
 */
public interface CasTelemetry {

    /** OTel status codes: 0 unset, 1 ok, 2 error. */
    enum SpanStatus {
        UNSET(0),
        OK(1),
        ERROR(2);

        private final int code;

        SpanStatus(int code) {
            this.code = code;
        }

        public int code() {
            return code;
        }
    }

    /** OTel span kinds; the CAS produces INTERNAL (2) and CLIENT (3) spans. */
    enum SpanKind {
        INTERNAL(1),
        SERVER(2),
        CLIENT(3);

        private final int code;

        SpanKind(int code) {
            this.code = code;
        }

        public int code() {
            return code;
        }
    }

    interface Span extends AutoCloseable {
        Span attribute(String key, String value);

        Span attribute(String key, long value);

        Span status(SpanStatus status, String description);

        String traceId();

        String spanId();

        @Override
        void close();
    }

    Span startSpan(String name, SpanKind kind, Optional<Span> parent);

    void counter(String name, String unit, long delta, Map<String, String> attributes);

    void histogram(String name, String unit, long value, Map<String, String> attributes);

    static CasTelemetry noop() {
        return NoopTelemetry.INSTANCE;
    }

    final class NoopTelemetry implements CasTelemetry {
        static final NoopTelemetry INSTANCE = new NoopTelemetry();

        private static final Span NOOP_SPAN = new Span() {
            @Override public Span attribute(String key, String value) { return this; }
            @Override public Span attribute(String key, long value) { return this; }
            @Override public Span status(SpanStatus status, String description) { return this; }
            @Override public String traceId() { return "0".repeat(32); }
            @Override public String spanId() { return "0".repeat(16); }
            @Override public void close() { }
        };

        private NoopTelemetry() {
        }

        @Override
        public Span startSpan(String name, SpanKind kind, Optional<Span> parent) {
            return NOOP_SPAN;
        }

        @Override
        public void counter(String name, String unit, long delta, Map<String, String> attributes) {
        }

        @Override
        public void histogram(String name, String unit, long value, Map<String, String> attributes) {
        }
    }

    /** Immutable record of a finished span, ready for export or assertion. */
    record FinishedSpan(String traceId, String spanId, String parentSpanId, String name, SpanKind kind,
                        long startUnixNanos, long endUnixNanos, Map<String, String> stringAttributes,
                        Map<String, Long> longAttributes, SpanStatus status, String statusDescription) {
        public FinishedSpan {
            stringAttributes = Map.copyOf(new TreeMap<>(stringAttributes));
            longAttributes = Map.copyOf(new TreeMap<>(longAttributes));
        }

        public long durationNanos() {
            return endUnixNanos - startUnixNanos;
        }
    }

    record MetricPoint(String name, String unit, boolean monotonicSum, long value,
                       Map<String, String> attributes, long timeUnixNanos) {
    }

    /**
     * Collects spans and metrics in memory. Used directly in tests and as the buffer an exporter
     * drains; ids come from an injectable generator so a test can assert exact trace ids.
     */
    final class Recording implements CasTelemetry {

        public interface IdGenerator {
            String traceId();

            String spanId();
        }

        /** Sequential ids, for deterministic assertions. */
        public static final class SequentialIds implements IdGenerator {
            private final AtomicLong traces = new AtomicLong();
            private final AtomicLong spans = new AtomicLong();

            @Override
            public String traceId() {
                return String.format("%032x", traces.incrementAndGet());
            }

            @Override
            public String spanId() {
                return String.format("%016x", spans.incrementAndGet());
            }
        }

        public static final class RandomIds implements IdGenerator {
            private final java.security.SecureRandom random = new java.security.SecureRandom();

            @Override
            public String traceId() {
                return hex(16);
            }

            @Override
            public String spanId() {
                return hex(8);
            }

            private String hex(int bytes) {
                byte[] value = new byte[bytes];
                random.nextBytes(value);
                return java.util.HexFormat.of().formatHex(value);
            }
        }

        private final IdGenerator ids;
        private final LongSupplier nanoClock;
        private final List<FinishedSpan> spans = Collections.synchronizedList(new ArrayList<>());
        private final Map<String, Long> counters = Collections.synchronizedMap(new LinkedHashMap<>());
        private final List<MetricPoint> points = Collections.synchronizedList(new ArrayList<>());

        public Recording(IdGenerator ids, LongSupplier nanoClock) {
            this.ids = Objects.requireNonNull(ids, "ids");
            this.nanoClock = Objects.requireNonNull(nanoClock, "nanoClock");
        }

        public static Recording deterministic(LongSupplier nanoClock) {
            return new Recording(new SequentialIds(), nanoClock);
        }

        @Override
        public Span startSpan(String name, SpanKind kind, Optional<Span> parent) {
            return new RecordingSpan(name, kind,
                    parent.map(Span::traceId).orElseGet(ids::traceId),
                    ids.spanId(),
                    parent.map(Span::spanId).orElse(""),
                    nanoClock.getAsLong());
        }

        @Override
        public void counter(String name, String unit, long delta, Map<String, String> attributes) {
            String key = name + attributeKey(attributes);
            counters.merge(key, delta, Long::sum);
            points.add(new MetricPoint(name, unit, true, counters.get(key), new TreeMap<>(attributes),
                    nanoClock.getAsLong()));
        }

        @Override
        public void histogram(String name, String unit, long value, Map<String, String> attributes) {
            points.add(new MetricPoint(name, unit, false, value, new TreeMap<>(attributes),
                    nanoClock.getAsLong()));
        }

        public List<FinishedSpan> spans() {
            synchronized (spans) {
                return List.copyOf(spans);
            }
        }

        public List<MetricPoint> metrics() {
            synchronized (points) {
                return List.copyOf(points);
            }
        }

        public Optional<FinishedSpan> span(String name) {
            return spans().stream().filter(span -> span.name().equals(name)).findFirst();
        }

        public long counterValue(String name, Map<String, String> attributes) {
            return counters.getOrDefault(name + attributeKey(attributes), 0L);
        }

        public void clear() {
            spans.clear();
            points.clear();
            counters.clear();
        }

        private static String attributeKey(Map<String, String> attributes) {
            return new TreeMap<>(attributes).toString();
        }

        private final class RecordingSpan implements Span {
            private final String name;
            private final SpanKind kind;
            private final String traceId;
            private final String spanId;
            private final String parentSpanId;
            private final long startNanos;
            private final Map<String, String> stringAttributes = new TreeMap<>();
            private final Map<String, Long> longAttributes = new TreeMap<>();
            private SpanStatus status = SpanStatus.UNSET;
            private String statusDescription = "";
            private boolean closed;

            private RecordingSpan(String name, SpanKind kind, String traceId, String spanId,
                                  String parentSpanId, long startNanos) {
                this.name = name;
                this.kind = kind;
                this.traceId = traceId;
                this.spanId = spanId;
                this.parentSpanId = parentSpanId;
                this.startNanos = startNanos;
            }

            @Override
            public Span attribute(String key, String value) {
                stringAttributes.put(key, value);
                return this;
            }

            @Override
            public Span attribute(String key, long value) {
                longAttributes.put(key, value);
                return this;
            }

            @Override
            public Span status(SpanStatus newStatus, String description) {
                this.status = newStatus;
                this.statusDescription = description == null ? "" : description;
                return this;
            }

            @Override
            public String traceId() {
                return traceId;
            }

            @Override
            public String spanId() {
                return spanId;
            }

            @Override
            public void close() {
                if (closed) {
                    // try-with-resources plus an explicit close would otherwise record the span
                    // twice and double every duration histogram built from it.
                    return;
                }
                closed = true;
                spans.add(new FinishedSpan(traceId, spanId, parentSpanId, name, kind, startNanos,
                        nanoClock.getAsLong(), stringAttributes, longAttributes, status, statusDescription));
            }
        }
    }
}
