import com.sun.source.tree.BinaryTree;
import com.sun.source.tree.BlockTree;
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.ExpressionTree;
import com.sun.source.tree.IdentifierTree;
import com.sun.source.tree.IfTree;
import com.sun.source.tree.ImportTree;
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
import com.sun.source.util.SourcePositions;
import com.sun.source.util.TreePathScanner;
import com.sun.source.util.Trees;

import javax.lang.model.element.Modifier;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public final class Analyzer {
    private Analyzer() {}

    public static void main(String[] args) throws Exception {
        try {
            run(args);
        } catch (CertifiedSubsetDomainException error) {
            System.err.println(error.getMessage());
            System.exit(2);
        }
    }

    private static void run(String[] args) throws Exception {
        if (args.length < 2 || args.length > 3 || (args.length == 3 && !args[2].equals("--emitted-target"))) {
            throw new IllegalArgumentException(
                    "usage: Analyzer.java <source> <function|--inventory> [--emitted-target]");
        }
        Path source = Path.of(args[0]).toAbsolutePath().normalize();
        String sourceText = Files.readString(source, StandardCharsets.UTF_8);
        String functionName = args[1];
        boolean inventoryMode = functionName.equals("--inventory");
        if (inventoryMode && args.length != 2) {
            throw new IllegalArgumentException("--inventory does not accept --emitted-target");
        }
        boolean emittedTarget = args.length == 3;
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) throw new IllegalStateException("JDK_COMPILER_UNAVAILABLE");
        DiagnosticCollector<JavaFileObject> diagnostics = new DiagnosticCollector<>();
        List<Map<String, Object>> functions = new ArrayList<>();
        List<Map<String, Object>> subjects = new ArrayList<>();
        try (StandardJavaFileManager files = compiler.getStandardFileManager(diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
            Iterable<? extends JavaFileObject> units = files.getJavaFileObjects(source);
            JavacTask task = (JavacTask) compiler.getTask(
                    null, files, diagnostics, List.of("--release", "21", "-proc:none", "-Xlint:none"), null, units);
            var trees = task.parse();
            task.analyze();
            SourcePositions positions = Trees.instance(task).getSourcePositions();
            for (var unit : trees) {
                SpanContext spans = new SpanContext(
                        unit,
                        positions,
                        sourceText,
                        source.getFileName().toString());
                if (inventoryMode) {
                    new ModuleScanner(subjects, spans).scan(unit, null);
                } else {
                    new FunctionScanner(functionName, functions, emittedTarget, spans).scan(unit, null);
                }
            }
        }
        List<String> errors = diagnostics.getDiagnostics().stream()
                .filter(item -> item.getKind() == Diagnostic.Kind.ERROR)
                .map(item -> item.getCode() + ":" + item.getLineNumber())
                .sorted()
                .toList();
        if (inventoryMode) {
            Map<String, Object> inventory = new LinkedHashMap<>();
            inventory.put("schema_version", "1.0.0");
            inventory.put("kind", "elmos.typed-pure-module-inventory");
            inventory.put("profile", "typed-pure-module-v1");
            inventory.put("source_language", "java");
            inventory.put("source_file", source.getFileName().toString());
            inventory.put("analyzer", "JDK JavacTask Tree API");
            inventory.put("analyzer_version", System.getProperty("java.version"));
            inventory.put("enumeration_status", errors.isEmpty() ? "PASSED" : "FAILED");
            inventory.put("subjects", subjects);
            inventory.put("diagnostics", errors);
            System.out.println(Json.write(inventory));
            return;
        }
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

    private static boolean typedPureMethodShape(MethodTree method) {
        return method.getBody() != null
                && method.getReturnType() != null
                && method.getModifiers().getFlags().contains(Modifier.STATIC)
                && method.getModifiers().getAnnotations().isEmpty()
                && method.getTypeParameters().isEmpty()
                && method.getThrows().isEmpty()
                && method.getReceiverParameter() == null
                && method.getDefaultValue() == null;
    }

    private record SpanContext(
            CompilationUnitTree unit,
            SourcePositions positions,
            String sourceText,
            String file) {}

    private static Map<String, Object> sourceSpan(Tree tree, SpanContext spans) {
        long startCharacter = spans.positions().getStartPosition(spans.unit(), tree);
        long endCharacter = spans.positions().getEndPosition(spans.unit(), tree);
        if (startCharacter < 0 || endCharacter <= startCharacter || endCharacter > spans.sourceText().length()) {
            throw new IllegalArgumentException("JAVA_SOURCE_SPAN_UNAVAILABLE:" + tree.getKind());
        }
        int startByte = spans.sourceText()
                .substring(0, Math.toIntExact(startCharacter))
                .getBytes(StandardCharsets.UTF_8).length;
        int endByte = spans.sourceText()
                .substring(0, Math.toIntExact(endCharacter))
                .getBytes(StandardCharsets.UTF_8).length;
        return Map.of(
                "file", spans.file(),
                "start_byte", startByte,
                "end_byte", endByte);
    }

    private static Map<String, Object> withSpan(
            Tree tree,
            SpanContext spans,
            Map<String, Object> value) {
        Map<String, Object> result = new LinkedHashMap<>(value);
        result.put("source_span", sourceSpan(tree, spans));
        return result;
    }

    private static final class FunctionScanner extends TreePathScanner<Void, Void> {
        private final String expectedName;
        private final List<Map<String, Object>> functions;
        private final boolean emittedTarget;
        private final SpanContext spans;

        private FunctionScanner(
                String expectedName,
                List<Map<String, Object>> functions,
                boolean emittedTarget,
                SpanContext spans) {
            this.expectedName = expectedName;
            this.functions = functions;
            this.emittedTarget = emittedTarget;
            this.spans = spans;
        }

        @Override
        public Void visitMethod(MethodTree method, Void unused) {
            if (!method.getName().contentEquals(expectedName) || method.getBody() == null) return null;
            if (!typedPureMethodShape(method)) {
                throw new IllegalArgumentException("JAVA_METHOD_SHAPE_OUTSIDE_CERTIFIED_SUBSET");
            }
            List<Map<String, Object>> parameters = new ArrayList<>();
            Map<String, String> environment = new LinkedHashMap<>();
            for (VariableTree parameter : method.getParameters()) {
                String parameterType = type(parameter.getType().toString());
                parameters.add(withSpan(
                        parameter,
                        spans,
                        Map.of(
                                "name", parameter.getName().toString(),
                                "type", parameterType)));
                environment.put(parameter.getName().toString(), parameterType);
            }
            Map<String, Object> function = new LinkedHashMap<>();
            function.put("name", method.getName().toString());
            function.put("parameters", parameters);
            function.put("return_type", type(method.getReturnType().toString()));
            function.put("body", statements(method.getBody().getStatements(), emittedTarget, environment, spans));
            functions.add(withSpan(method, spans, function));
            return null;
        }
    }

    private static final class ModuleScanner extends TreePathScanner<Void, Void> {
        private final List<Map<String, Object>> subjects;
        private final SpanContext spans;
        private final List<String> scopes = new ArrayList<>();

        private ModuleScanner(List<Map<String, Object>> subjects, SpanContext spans) {
            this.subjects = subjects;
            this.spans = spans;
        }

        private String qualified(String name) {
            List<String> parts = new ArrayList<>(scopes);
            parts.add(name);
            return String.join(".", parts);
        }

        private void add(
                Tree tree,
                String name,
                String declarationKind,
                boolean analyzable,
                Map<String, Object> signature) {
            Map<String, Object> subject = new LinkedHashMap<>();
            subject.put("name", name);
            subject.put("qualified_name", qualified(name));
            subject.put("declaration_kind", declarationKind);
            subject.put("analyzable", analyzable);
            subject.put("source_span", sourceSpan(tree, spans));
            Map<String, Object> completeSignature = new LinkedHashMap<>(signature);
            completeSignature.putIfAbsent("visibility", "not-applicable");
            completeSignature.putIfAbsent("storage", "not-applicable");
            subject.put("signature", completeSignature);
            subjects.add(subject);
        }

        private static String visibility(java.util.Set<Modifier> modifiers) {
            if (modifiers.contains(Modifier.PRIVATE)) return "private";
            if (modifiers.contains(Modifier.PROTECTED)) return "protected";
            if (modifiers.contains(Modifier.PUBLIC)) return "public";
            return "package-private";
        }

        private static String storage(java.util.Set<Modifier> modifiers) {
            return modifiers.contains(Modifier.STATIC) ? "static" : "instance";
        }

        private static List<String> modifierNames(java.util.Set<Modifier> modifiers) {
            return modifiers.stream()
                    .map(item -> item.name().toLowerCase(Locale.ROOT))
                    .sorted()
                    .toList();
        }

        private static List<String> annotationNames(
                com.sun.source.tree.ModifiersTree modifiers) {
            return modifiers.getAnnotations().stream()
                    .map(item -> item.getAnnotationType().toString())
                    .sorted()
                    .toList();
        }

        private static Map<String, Object> typeSignature(
                com.sun.source.tree.ClassTree type,
                boolean nested) {
            var modifiers = type.getModifiers().getFlags();
            Map<String, Object> signature = new LinkedHashMap<>();
            signature.put("type_kind", type.getKind().name());
            signature.put("visibility", visibility(modifiers));
            signature.put("storage", nested ? "nested" : "top-level");
            signature.put("modifiers", modifierNames(modifiers));
            signature.put("final", modifiers.contains(Modifier.FINAL));
            signature.put("abstract", modifiers.contains(Modifier.ABSTRACT));
            signature.put(
                    "extends",
                    type.getExtendsClause() == null ? "" : type.getExtendsClause().toString());
            signature.put(
                    "implements",
                    type.getImplementsClause().stream().map(Object::toString).toList());
            signature.put(
                    "type_parameters",
                    type.getTypeParameters().stream().map(Object::toString).toList());
            signature.put("annotations", annotationNames(type.getModifiers()));
            signature.put(
                    "permits",
                    type.getPermitsClause().stream().map(Object::toString).toList());
            return signature;
        }

        @Override
        public Void visitCompilationUnit(CompilationUnitTree unit, Void unused) {
            for (var annotation : unit.getPackageAnnotations()) {
                String name = annotation.getAnnotationType().toString();
                add(
                        annotation,
                        name,
                        "compilation-unit-annotation",
                        false,
                        Map.of());
            }
            if (unit.getPackageName() != null) {
                String name = unit.getPackageName().toString();
                add(unit.getPackageName(), name, "package", false, Map.of());
            }
            if (unit.getModule() != null) {
                String name = unit.getModule().getName().toString();
                add(unit.getModule(), name, "module-declaration", false, Map.of());
            }
            return super.visitCompilationUnit(unit, unused);
        }

        @Override
        public Void visitImport(ImportTree imported, Void unused) {
            String name = imported.getQualifiedIdentifier().toString();
            add(imported, name, "import", false, Map.of("static", imported.isStatic()));
            return null;
        }

        @Override
        public Void visitClass(com.sun.source.tree.ClassTree type, Void unused) {
            String name = type.getSimpleName().toString();
            boolean nested = !scopes.isEmpty();
            String declarationKind = nested
                    ? "nested-type"
                    : type.getKind() == Tree.Kind.CLASS
                            ? "top-level-class-wrapper"
                            : "top-level-type-obligation";
            add(type, name, declarationKind, false, typeSignature(type, nested));
            scopes.add(name);
            super.visitClass(type, unused);
            scopes.remove(scopes.size() - 1);
            return null;
        }

        @Override
        public Void visitVariable(VariableTree variable, Void unused) {
            Tree parent = getCurrentPath().getParentPath().getLeaf();
            if (parent instanceof com.sun.source.tree.ClassTree) {
                add(
                        variable,
                        variable.getName().toString(),
                        "field",
                        false,
                        Map.of(
                                "source_type", variable.getType().toString(),
                                "visibility", visibility(variable.getModifiers().getFlags()),
                                "storage", storage(variable.getModifiers().getFlags())));
            }
            return null;
        }

        @Override
        public Void visitBlock(BlockTree block, Void unused) {
            Tree parent = getCurrentPath().getParentPath().getLeaf();
            if (parent instanceof com.sun.source.tree.ClassTree) {
                add(
                        block,
                        block.isStatic() ? "<static-initializer>" : "<instance-initializer>",
                        block.isStatic() ? "static-initializer" : "instance-initializer",
                        false,
                        Map.of());
            }
            return null;
        }

        @Override
        public Void visitMethod(MethodTree method, Void unused) {
            long startCharacter = spans.positions().getStartPosition(spans.unit(), method);
            long endCharacter = spans.positions().getEndPosition(spans.unit(), method);
            if (method.getReturnType() == null
                    && (startCharacter < 0 || endCharacter <= startCharacter)) {
                // JavacTask.analyze() injects a default constructor into classes
                // that do not declare one. It has no source bytes and is not a
                // repository declaration, so it must not enter the inventory.
                return null;
            }
            String name = method.getName().toString();
            List<Map<String, Object>> parameters = new ArrayList<>();
            for (VariableTree parameter : method.getParameters()) {
                parameters.add(Map.of(
                        "name", parameter.getName().toString(),
                        "source_type", parameter.getType().toString()));
            }
            boolean analyzable = typedPureMethodShape(method);
            var modifiers = method.getModifiers().getFlags();
            Map<String, Object> signature = new LinkedHashMap<>();
            signature.put("parameters", parameters);
            signature.put(
                    "source_return_type",
                    method.getReturnType() == null ? "" : method.getReturnType().toString());
            signature.put("static", modifiers.contains(Modifier.STATIC));
            signature.put("visibility", visibility(modifiers));
            signature.put("storage", storage(modifiers));
            signature.put("modifiers", modifierNames(modifiers));
            signature.put("annotations", annotationNames(method.getModifiers()));
            signature.put(
                    "type_parameters",
                    method.getTypeParameters().stream().map(Object::toString).toList());
            signature.put(
                    "throws",
                    method.getThrows().stream().map(Object::toString).toList());
            signature.put("default_value", method.getDefaultValue() != null);
            signature.put("receiver_parameter", method.getReceiverParameter() != null);
            add(
                    method,
                    name,
                    method.getReturnType() == null ? "constructor" : "method",
                    analyzable,
                    signature);
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
     * <p>Only primitive {@code long} maps to canonical {@code integer}. Narrow
     * integer types are rejected because widening them would erase source
     * overflow behaviour before equivalence is checked.
     */
    private static String type(String sourceType) {
        String normalized = sourceType.replace("java.lang.", "").replace("java.math.", "").trim();
        return switch (normalized) {
            case "long" -> "integer";
            case "double" -> "number";
            case "boolean" -> "boolean";
            case "String" -> "string";
            case "float" -> throw new IllegalArgumentException(
                    "JAVA_FLOAT_PRECISION_OUTSIDE_CERTIFIED_SUBSET:" + sourceType);
            case "int" -> throw new CertifiedSubsetDomainException(
                    "JAVA_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:int");
            case "byte", "short", "char" -> throw new IllegalArgumentException(
                    "JAVA_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:" + sourceType);
            case "CharSequence" -> throw new IllegalArgumentException(
                    "JAVA_INTERFACE_STRING_OUTSIDE_CERTIFIED_SUBSET:" + sourceType);
            case "BigDecimal", "BigInteger" -> throw new IllegalArgumentException(
                    "JAVA_EXACT_ARITHMETIC_TYPE_OUTSIDE_CERTIFIED_SUBSET:" + sourceType);
            case "Byte", "Short", "Integer", "Long", "Float", "Double", "Boolean", "Character" ->
                    throw new IllegalArgumentException(
                            "JAVA_BOXED_NULLABLE_TYPE_OUTSIDE_CERTIFIED_SUBSET:" + sourceType);
            default -> throw new IllegalArgumentException("JAVA_UNSUPPORTED_TYPE:" + sourceType);
        };
    }

    private static final class CertifiedSubsetDomainException extends RuntimeException {
        private CertifiedSubsetDomainException(String reason) {
            super(reason, null, false, false);
        }
    }

    private static List<Map<String, Object>> statements(
            List<? extends StatementTree> source,
            boolean emittedTarget,
            Map<String, String> environment,
            SpanContext spans) {
        List<Map<String, Object>> result = new ArrayList<>();
        for (StatementTree statement : source) {
            if (statement instanceof ReturnTree returning && returning.getExpression() != null) {
                result.add(withSpan(
                        statement,
                        spans,
                        Map.of(
                                "kind", "return",
                                "expression", expression(
                                        returning.getExpression(), emittedTarget, environment, spans))));
            } else if (statement instanceof IfTree conditional) {
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("kind", "if");
                item.put("condition", expression(
                        conditional.getCondition(), emittedTarget, environment, spans));
                item.put("then", statementBody(
                        conditional.getThenStatement(), emittedTarget, environment, spans));
                item.put("else", conditional.getElseStatement() == null
                        ? List.of()
                        : statementBody(conditional.getElseStatement(), emittedTarget, environment, spans));
                result.add(withSpan(statement, spans, item));
            } else {
                throw new IllegalArgumentException("JAVA_UNSUPPORTED_STATEMENT:" + statement.getKind());
            }
        }
        return result;
    }

    private static List<Map<String, Object>> statementBody(
            StatementTree statement,
            boolean emittedTarget,
            Map<String, String> environment,
            SpanContext spans) {
        if (statement instanceof BlockTree block) {
            return statements(block.getStatements(), emittedTarget, environment, spans);
        }
        return statements(List.of(statement), emittedTarget, environment, spans);
    }

    private static boolean isStringExpression(
            ExpressionTree tree,
            Map<String, String> environment) {
        if (tree instanceof ParenthesizedTree parenthesized) {
            return isStringExpression(parenthesized.getExpression(), environment);
        }
        if (tree instanceof LiteralTree literal) return literal.getValue() instanceof String;
        return tree instanceof IdentifierTree identifier
                && "string".equals(environment.get(identifier.getName().toString()));
    }

    private static Map<String, Object> expression(
            ExpressionTree tree,
            boolean emittedTarget,
            Map<String, String> environment,
            SpanContext spans) {
        if (tree instanceof ParenthesizedTree parenthesized) {
            Map<String, Object> nested = expression(
                    parenthesized.getExpression(), emittedTarget, environment, spans);
            Map<String, Object> value = new LinkedHashMap<>(nested);
            value.put("source_span", sourceSpan(tree, spans));
            return value;
        }
        if (tree instanceof IdentifierTree identifier) {
            return withSpan(
                    tree,
                    spans,
                    Map.of("kind", "name", "value", identifier.getName().toString()));
        }
        if (tree instanceof LiteralTree literal) {
            if (literal.getValue() == null) {
                throw new IllegalArgumentException("JAVA_NULL_LITERAL_OUTSIDE_CERTIFIED_SUBSET");
            }
            return withSpan(
                    tree,
                    spans,
                    Map.of("kind", "literal", "value", literal.getValue()));
        }
        if (tree instanceof BinaryTree binary) {
            String symbol = operator(binary.getKind());
            if ((symbol.equals("==") || symbol.equals("!="))
                    && (isStringExpression(binary.getLeftOperand(), environment)
                            || isStringExpression(binary.getRightOperand(), environment))) {
                throw new IllegalArgumentException(
                        "JAVA_STRING_REFERENCE_EQUALITY_OUTSIDE_CERTIFIED_SUBSET");
            }
            return withSpan(
                    tree,
                    spans,
                    Map.of(
                            "kind", "binary",
                            "operator", symbol,
                            "left", expression(binary.getLeftOperand(), emittedTarget, environment, spans),
                            "right", expression(binary.getRightOperand(), emittedTarget, environment, spans)));
        }
        if (emittedTarget && tree instanceof MethodInvocationTree invocation) {
            return emittedInvocation(invocation, environment, spans);
        }
        if (
                emittedTarget
                        && tree instanceof UnaryTree unary
                        && unary.getKind() == Tree.Kind.LOGICAL_COMPLEMENT
                        && unary.getExpression() instanceof MethodInvocationTree invocation) {
            return emittedStringEquality(invocation, true, environment, spans, tree);
        }
        throw new IllegalArgumentException("JAVA_UNSUPPORTED_EXPRESSION:" + tree.getKind());
    }

    private static Map<String, Object> emittedInvocation(
            MethodInvocationTree invocation,
            Map<String, String> environment,
            SpanContext spans) {
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
            return withSpan(
                    invocation,
                    spans,
                    Map.of(
                            "kind", "binary",
                            "operator", operator,
                            "left", expression(invocation.getArguments().get(0), true, environment, spans),
                            "right", expression(invocation.getArguments().get(1), true, environment, spans)));
        }
        if (callee.equals("Migrated.elmosNonZero")) {
            if (invocation.getArguments().size() != 1) {
                throw new IllegalArgumentException("JAVA_EMITTED_HELPER_ARITY:" + callee);
            }
            Map<String, Object> value = new LinkedHashMap<>(expression(
                    invocation.getArguments().get(0), true, environment, spans));
            value.put("source_span", sourceSpan(invocation, spans));
            return value;
        }
        if (
                invocation.getMethodSelect() instanceof MemberSelectTree member
                        && member.getIdentifier().contentEquals("equals")) {
            return emittedStringEquality(invocation, false, environment, spans, invocation);
        }
        throw new IllegalArgumentException("JAVA_EMITTED_HELPER_UNRECOGNIZED:" + callee);
    }

    private static Map<String, Object> emittedStringEquality(
            MethodInvocationTree invocation,
            boolean negated,
            Map<String, String> environment,
            SpanContext spans,
            Tree spanTree) {
        if (
                !(invocation.getMethodSelect() instanceof MemberSelectTree member)
                        || !member.getIdentifier().contentEquals("equals")
                        || invocation.getArguments().size() != 1) {
            throw new IllegalArgumentException("JAVA_EMITTED_STRING_EQUALITY_INVALID");
        }
        return withSpan(
                spanTree,
                spans,
                Map.of(
                        "kind", "binary",
                        "operator", negated ? "!=" : "==",
                        "left", expression(member.getExpression(), true, environment, spans),
                        "right", expression(invocation.getArguments().get(0), true, environment, spans)));
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
