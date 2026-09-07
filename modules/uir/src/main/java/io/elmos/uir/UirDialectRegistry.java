package io.elmos.uir;

import java.util.*;

import static io.elmos.uir.UirModels.Dialect;

public final class UirDialectRegistry {
    private final Map<String, Dialect> dialects = new TreeMap<>();

    public UirDialectRegistry() { coreDialects().forEach(this::register); }

    public synchronized void register(Dialect dialect) {
        Objects.requireNonNull(dialect); if (dialect.name() == null || !dialect.name().matches("uir(?:\\.[a-z][a-z0-9-]*)+")) throw new IllegalArgumentException("DIALECT_NAME_INVALID");
        if (dialect.version() == null || !dialect.version().matches("[0-9]+\\.[0-9]+")) throw new IllegalArgumentException("DIALECT_VERSION_INVALID");
        if (new HashSet<>(dialect.operations()).size() != dialect.operations().size()) throw new IllegalArgumentException("DIALECT_OPERATION_DUPLICATE");
        Dialect previous = dialects.putIfAbsent(dialect.name(), dialect); if (previous != null && !previous.equals(dialect)) throw new IllegalStateException("DIALECT_ALREADY_REGISTERED:" + dialect.name());
    }
    public Dialect require(String name) { Dialect dialect = dialects.get(name); if (dialect == null) throw new IllegalArgumentException("DIALECT_UNKNOWN:" + name); return dialect; }
    public boolean supports(String dialect, String opcode) { Dialect value = dialects.get(dialect); return value != null && (value.operations().contains(opcode) || value.opaqueForwardCompatible()); }
    public List<Dialect> all() { return List.copyOf(dialects.values()); }

    private static List<Dialect> coreDialects() {
        List<String> lowering = List.of("java", "python", "csharp", "typescript");
        return List.of(
                dialect("uir.core", List.of("module","declare","constant","reference","assign","call","return","branch","conditional","loop","cast","type_test","unknown"), lowering),
                dialect("uir.scf", List.of("if","switch","match","while","do_while","for","foreach","try","resource_scope","lock"), lowering),
                dialect("uir.object", List.of("type","construct","field_get","field_set","property_get","property_set","virtual_call","interface_call","super_call","event_subscribe","event_emit"), lowering),
                dialect("uir.collection", List.of("create","get","set","add","remove","iterate","map","filter","reduce","comprehension"), lowering),
                dialect("uir.exception", List.of("try","catch","finally","throw","rethrow","filter","resource_scope","promise_rejection"), lowering),
                dialect("uir.async", List.of("callable","await","spawn","join","cancel","callback_register","callback_invoke","yield","generator","stream"), lowering),
                dialect("uir.effect", List.of("read","write","allocate","io","network","database","random","time","reflect","dynamic","synchronize"), lowering),
                dialect("uir.concurrent", List.of("lock","unlock","atomic_read","atomic_write","compare_exchange","fence","thread_local","channel_send","channel_receive"), lowering),
                dialect("uir.dynamic", List.of("member_get","member_set","call","import","eval","proxy","monkey_patch","runtime_type"), lowering),
                dialect("uir.framework", List.of("endpoint","dependency","transaction","repository","entity","message_handler","scheduler","validation","authorization"), lowering),
                language("java", lowering), language("python", lowering), language("csharp", lowering),
                language("javascript", lowering), language("typescript", lowering));
    }
    private static Dialect dialect(String name, List<String> operations, List<String> lowering) { return new Dialect(name, "1.0", operations, List.of(), name.substring(4) + "-dialect-verifier", lowering, false); }
    private static Dialect language(String language, List<String> lowering) { return new Dialect("uir.lang." + language, "1.0", List.of("opaque"), List.of("opaque"), "opaque-language-verifier", lowering, true); }
}
