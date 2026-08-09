import com.sun.source.tree.BinaryTree;
import com.sun.source.tree.BlockTree;
import com.sun.source.tree.ExpressionTree;
import com.sun.source.tree.IdentifierTree;
import com.sun.source.tree.IfTree;
import com.sun.source.tree.LiteralTree;
import com.sun.source.tree.MemberSelectTree;
import com.sun.source.tree.MethodInvocationTree;
import com.sun.source.tree.MethodTree;
import com.sun.source.tree.ParenthesizedTree;
import com.sun.source.tree.ReturnTree;
import com.sun.source.tree.StatementTree;
import com.sun.source.tree.Tree;
import com.sun.source.tree.UnaryTree;
import com.sun.source.tree.VariableTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.TreePathScanner;

import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public final class Analyzer {
    private Analyzer() {}

    public static void main(String[] args) throws Exception {
        if (args.length < 2 || args.length > 3 || (args.length == 3 && !args[2].equals("--emitted-target"))) {
            throw new IllegalArgumentException("usage: Analyzer.java <source> <function> [--emitted-target]");
        }
        Path source = Path.of(args[0]).toAbsolutePath().normalize();
        String functionName = args[1];
        boolean emittedTarget = args.length == 3;
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) throw new IllegalStateException("JDK_COMPILER_UNAVAILABLE");
        DiagnosticCollector<JavaFileObject> diagnostics = new DiagnosticCollector<>();
        List<Map<String, Object>> functions = new ArrayList<>();
        try (StandardJavaFileManager files = compiler.getStandardFileManager(diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
            Iterable<? extends JavaFileObject> units = files.getJavaFileObjects(source);
            JavacTask task = (JavacTask) compiler.getTask(
                    null, files, diagnostics, List.of("--release", "21", "-proc:none", "-Xlint:none"), null, units);
            var trees = task.parse();
            task.analyze();
            for (var unit : trees) {
                new FunctionScanner(functionName, functions, emittedTarget).scan(unit, null);
            }
        }
        List<String> errors = diagnostics.getDiagnostics().stream()
                .filter(item -> item.getKind() == Diagnostic.Kind.ERROR)
                .map(item -> item.getCode() + ":" + item.getLineNumber())
                .sorted()
                .toList();
        if (functions.isEmpty()) errors = append(errors, "FUNCTION_NOT_FOUND:" + functionName);
        Map<String, Object> output = new LinkedHashMap<>();
        output.put("schema_version", "1.0.0");
        output.put("source_language", "java");
        output.put("source_file", source.getFileName().toString());
        output.put("analyzer", "JDK JavacTask Tree API");
        output.put("analyzer_version", System.getProperty("java.version"));
        output.put("functions", functions);
        output.put("diagnostics", errors);
        System.out.println(Json.write(output));
    }

    private static List<String> append(List<String> values, String value) {
        List<String> copy = new ArrayList<>(values);
        copy.add(value);
        return List.copyOf(copy);
    }

    private static final class FunctionScanner extends TreePathScanner<Void, Void> {
        private final String expectedName;
        private final List<Map<String, Object>> functions;
        private final boolean emittedTarget;

        private FunctionScanner(
                String expectedName,
                List<Map<String, Object>> functions,
                boolean emittedTarget) {
            this.expectedName = expectedName;
            this.functions = functions;
            this.emittedTarget = emittedTarget;
        }

        @Override
        public Void visitMethod(MethodTree method, Void unused) {
            if (!method.getName().contentEquals(expectedName) || method.getBody() == null) return null;
            List<Map<String, Object>> parameters = new ArrayList<>();
            for (VariableTree parameter : method.getParameters()) {
                parameters.add(Map.of(
                        "name", parameter.getName().toString(),
                        "type", type(parameter.getType().toString())));
            }
            Map<String, Object> function = new LinkedHashMap<>();
            function.put("name", method.getName().toString());
            function.put("parameters", parameters);
            function.put("return_type", type(method.getReturnType().toString()));
            function.put("body", statements(method.getBody().getStatements(), emittedTarget));
            functions.add(function);
            return null;
        }
    }

    /**
     * Lifts a Java source type to a canonical type. Case is significant here:
     * the boxed types differ from the primitives in exactly the way that
     * matters, so this must not lowercase first (an earlier revision did, and
     * silently lifted a nullable {@code Integer} to the primitive canonical
     * {@code integer}).
     *
     * <p>Three families are refused rather than approximated:
     * <ul>
     *   <li>{@code float} -- 24-bit significand. The canonical {@code number}
     *       is binary64, and {@code 0.1f + 0.2f} does not equal
     *       {@code 0.1 + 0.2}, so widening changes results for in-range
     *       values.</li>
     *   <li>{@code BigDecimal} -- exact base-10 arithmetic with no binary
     *       floating-point equivalent in any target of this profile.</li>
     *   <li>the boxed wrappers -- they are nullable, and the certified subset
     *       has no null (see {@code NULL_LITERAL_OUTSIDE_CERTIFIED_SUBSET});
     *       lifting {@code Integer} to a primitive silently drops that
     *       state.</li>
     * </ul>
     *
     * <p>{@code byte}/{@code short}/{@code int} widen to the canonical 64-bit
     * {@code integer}. That is exact for every value; only 32-bit overflow
     * wraparound differs, which is documented in the engine README.
     */
    private static String type(String sourceType) {
        String normalized = sourceType.replace("java.lang.", "").replace("java.math.", "").trim();
        return switch (normalized) {
            case "byte", "short", "int", "long" -> "integer";
            case "double" -> "number";
            case "boolean" -> "boolean";
            case "String", "CharSequence" -> "string";
            case "float" -> throw new IllegalArgumentException(
                    "JAVA_FLOAT_PRECISION_OUTSIDE_CERTIFIED_SUBSET:" + sourceType);
            case "BigDecimal", "BigInteger" -> throw new IllegalArgumentException(
                    "JAVA_EXACT_ARITHMETIC_TYPE_OUTSIDE_CERTIFIED_SUBSET:" + sourceType);
            case "Byte", "Short", "Integer", "Long", "Float", "Double", "Boolean", "Character" ->
                    throw new IllegalArgumentException(
                            "JAVA_BOXED_NULLABLE_TYPE_OUTSIDE_CERTIFIED_SUBSET:" + sourceType);
            default -> throw new IllegalArgumentException("JAVA_UNSUPPORTED_TYPE:" + sourceType);
        };
    }

    private static List<Map<String, Object>> statements(
            List<? extends StatementTree> source,
            boolean emittedTarget) {
        List<Map<String, Object>> result = new ArrayList<>();
        for (StatementTree statement : source) {
            if (statement instanceof ReturnTree returning && returning.getExpression() != null) {
                result.add(Map.of(
                        "kind", "return",
                        "expression", expression(returning.getExpression(), emittedTarget)));
            } else if (statement instanceof IfTree conditional) {
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("kind", "if");
                item.put("condition", expression(conditional.getCondition(), emittedTarget));
                item.put("then", statementBody(conditional.getThenStatement(), emittedTarget));
                item.put("else", conditional.getElseStatement() == null
                        ? List.of()
                        : statementBody(conditional.getElseStatement(), emittedTarget));
                result.add(item);
            } else {
                throw new IllegalArgumentException("JAVA_UNSUPPORTED_STATEMENT:" + statement.getKind());
            }
        }
        return result;
    }

    private static List<Map<String, Object>> statementBody(
            StatementTree statement,
            boolean emittedTarget) {
        if (statement instanceof BlockTree block) return statements(block.getStatements(), emittedTarget);
        return statements(List.of(statement), emittedTarget);
    }

    private static Map<String, Object> expression(ExpressionTree tree, boolean emittedTarget) {
        if (tree instanceof ParenthesizedTree parenthesized) {
            return expression(parenthesized.getExpression(), emittedTarget);
        }
        if (tree instanceof IdentifierTree identifier) return Map.of("kind", "name", "value", identifier.getName().toString());
        if (tree instanceof LiteralTree literal) return Map.of("kind", "literal", "value", literal.getValue());
        if (tree instanceof BinaryTree binary) {
            return Map.of(
                    "kind", "binary",
                    "operator", operator(binary.getKind()),
                    "left", expression(binary.getLeftOperand(), emittedTarget),
                    "right", expression(binary.getRightOperand(), emittedTarget));
        }
        if (emittedTarget && tree instanceof MethodInvocationTree invocation) {
            return emittedInvocation(invocation);
        }
        if (
                emittedTarget
                        && tree instanceof UnaryTree unary
                        && unary.getKind() == Tree.Kind.LOGICAL_COMPLEMENT
                        && unary.getExpression() instanceof MethodInvocationTree invocation) {
            return emittedStringEquality(invocation, true);
        }
        throw new IllegalArgumentException("JAVA_UNSUPPORTED_EXPRESSION:" + tree.getKind());
    }

    private static Map<String, Object> emittedInvocation(MethodInvocationTree invocation) {
        String callee = invocation.getMethodSelect().toString();
        String operator = switch (callee) {
            case "Math.addExact" -> "+";
            case "Math.subtractExact" -> "-";
            case "Math.multiplyExact" -> "*";
            case "Migrated.elmosCheckedDiv" -> "/";
            case "Migrated.elmosCheckedMod" -> "%";
            default -> null;
        };
        if (operator != null) {
            if (invocation.getArguments().size() != 2) {
                throw new IllegalArgumentException("JAVA_EMITTED_HELPER_ARITY:" + callee);
            }
            return Map.of(
                    "kind", "binary",
                    "operator", operator,
                    "left", expression(invocation.getArguments().get(0), true),
                    "right", expression(invocation.getArguments().get(1), true));
        }
        if (callee.equals("Migrated.elmosNonZero")) {
            if (invocation.getArguments().size() != 1) {
                throw new IllegalArgumentException("JAVA_EMITTED_HELPER_ARITY:" + callee);
            }
            return expression(invocation.getArguments().get(0), true);
        }
        if (
                invocation.getMethodSelect() instanceof MemberSelectTree member
                        && member.getIdentifier().contentEquals("equals")) {
            return emittedStringEquality(invocation, false);
        }
        throw new IllegalArgumentException("JAVA_EMITTED_HELPER_UNRECOGNIZED:" + callee);
    }

    private static Map<String, Object> emittedStringEquality(
            MethodInvocationTree invocation,
            boolean negated) {
        if (
                !(invocation.getMethodSelect() instanceof MemberSelectTree member)
                        || !member.getIdentifier().contentEquals("equals")
                        || invocation.getArguments().size() != 1) {
            throw new IllegalArgumentException("JAVA_EMITTED_STRING_EQUALITY_INVALID");
        }
        return Map.of(
                "kind", "binary",
                "operator", negated ? "!=" : "==",
                "left", expression(member.getExpression(), true),
                "right", expression(invocation.getArguments().get(0), true));
    }

    private static String operator(Tree.Kind kind) {
        return switch (kind) {
            case PLUS -> "+";
            case MINUS -> "-";
            case MULTIPLY -> "*";
            case DIVIDE -> "/";
            case REMAINDER -> "%";
            case LESS_THAN -> "<";
            case LESS_THAN_EQUAL -> "<=";
            case GREATER_THAN -> ">";
            case GREATER_THAN_EQUAL -> ">=";
            case EQUAL_TO -> "==";
            case NOT_EQUAL_TO -> "!=";
            case CONDITIONAL_AND -> "&&";
            case CONDITIONAL_OR -> "||";
            default -> throw new IllegalArgumentException("JAVA_UNSUPPORTED_OPERATOR:" + kind);
        };
    }

    private static final class Json {
        private Json() {}

        static String write(Object value) {
            if (value == null) return "null";
            if (value instanceof String text) return quote(text);
            if (value instanceof Number || value instanceof Boolean) return value.toString();
            if (value instanceof Map<?, ?> map) {
                List<String> entries = new ArrayList<>();
                for (var entry : map.entrySet()) entries.add(quote(entry.getKey().toString()) + ":" + write(entry.getValue()));
                return "{" + String.join(",", entries) + "}";
            }
            if (value instanceof Iterable<?> items) {
                List<String> entries = new ArrayList<>();
                for (Object item : items) entries.add(write(item));
                return "[" + String.join(",", entries) + "]";
            }
            throw new IllegalArgumentException("JSON_UNSUPPORTED_VALUE:" + value.getClass());
        }

        private static String quote(String value) {
            StringBuilder result = new StringBuilder("\"");
            for (int index = 0; index < value.length(); index++) {
                char character = value.charAt(index);
                switch (character) {
                    case '"' -> result.append("\\\"");
                    case '\\' -> result.append("\\\\");
                    case '\n' -> result.append("\\n");
                    case '\r' -> result.append("\\r");
                    case '\t' -> result.append("\\t");
                    default -> {
                        if (character < 0x20) result.append(String.format("\\u%04x", (int) character));
                        else result.append(character);
                    }
                }
            }
            return result.append('"').toString();
        }
    }
}
