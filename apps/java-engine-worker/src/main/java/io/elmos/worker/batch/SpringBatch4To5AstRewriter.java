package io.elmos.worker.batch;

import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.ImportTree;
import com.sun.source.tree.MemberSelectTree;
import com.sun.source.tree.MethodInvocationTree;
import com.sun.source.tree.Tree;
import com.sun.source.tree.VariableTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.SourcePositions;
import com.sun.source.util.TreePathScanner;
import com.sun.source.util.Trees;

import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.ToolProvider;
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

/** AST-positioned Spring Batch 4 to 5 builder migration. */
public final class SpringBatch4To5AstRewriter {
    public record RewriteResult(
            boolean modified,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            List<String> blockingObligations
    ) {}

    private SpringBatch4To5AstRewriter() {}

    public static RewriteResult modernize(Path projectRoot) {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        Set<String> modified = new LinkedHashSet<>();
        List<String> rules = new ArrayList<>();
        List<String> blockers = new ArrayList<>();
        if (!Files.isDirectory(projectRoot)) {
            return new RewriteResult(false, modified, rules, List.of("project root does not exist"));
        }
        try (var files = Files.walk(projectRoot)) {
            for (Path file : files.filter(Files::isRegularFile)
                    .filter(path -> path.getFileName().toString().endsWith(".java")).toList()) {
                String source = Files.readString(file, StandardCharsets.UTF_8);
                if (!source.contains("JobBuilderFactory") && !source.contains("StepBuilderFactory")) continue;
                FileRewrite rewrite = rewrite(source, relative(projectRoot, file));
                blockers.addAll(rewrite.blockers);
                if (rewrite.blockers.isEmpty() && !rewrite.source.equals(source)) {
                    Files.writeString(file, rewrite.source, StandardCharsets.UTF_8);
                    modified.add(relative(projectRoot, file));
                    rules.addAll(rewrite.rules);
                }
            }
        } catch (IOException e) {
            blockers.add("IO:" + e.getClass().getSimpleName());
        }
        return new RewriteResult(!modified.isEmpty(), Set.copyOf(modified), List.copyOf(rules), List.copyOf(blockers));
    }

    static FileRewrite rewrite(String source, String sourceName) {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            return new FileRewrite(source, List.of(), List.of(sourceName + ": JDK compiler API unavailable"));
        }
        DiagnosticCollector<JavaFileObject> diagnostics = new DiagnosticCollector<>();
        JavaFileObject input = new SourceFile(sourceName, source);
        try {
            JavacTask task = (JavacTask) compiler.getTask(null, null, diagnostics,
                    List.of("-proc:none"), null, List.of(input));
            CompilationUnitTree unit = task.parse().iterator().next();
            boolean syntaxError = diagnostics.getDiagnostics().stream()
                    .anyMatch(diagnostic -> diagnostic.getKind() == javax.tools.Diagnostic.Kind.ERROR);
            if (syntaxError) {
                return new FileRewrite(source, List.of(), List.of(sourceName + ": Java syntax errors block AST rewrite"));
            }
            Trees trees = Trees.instance(task);
            SourcePositions positions = trees.getSourcePositions();
            Scanner scanner = new Scanner(source, unit, positions);
            scanner.scan(unit, null);
            if (scanner.needsTransactionManager && !scanner.hasTransactionManager) {
                scanner.blockers.add(sourceName
                        + ": chunk builder requires an explicit PlatformTransactionManager binding");
            }
            if (!scanner.blockers.isEmpty()) {
                return new FileRewrite(source, List.of(), List.copyOf(scanner.blockers));
            }
            String rewritten = apply(source, scanner.edits);
            rewritten = normalizeImports(rewritten, scanner.jobFactorySeen, scanner.stepFactorySeen);
            List<String> rules = new ArrayList<>();
            if (scanner.jobFactorySeen) rules.add("SPRING_BATCH5_JOB_BUILDER_JOB_REPOSITORY");
            if (scanner.stepFactorySeen) rules.add("SPRING_BATCH5_STEP_BUILDER_JOB_REPOSITORY");
            if (scanner.needsTransactionManager) rules.add("SPRING_BATCH5_CHUNK_TRANSACTION_MANAGER");
            return new FileRewrite(rewritten, rules, List.of());
        } catch (Exception e) {
            return new FileRewrite(source, List.of(), List.of(sourceName + ": AST rewrite failed: " + e.getClass().getSimpleName()));
        }
    }

    private static String normalizeImports(String source, boolean job, boolean step) {
        String result = source
                .replace("import org.springframework.batch.core.configuration.annotation.JobBuilderFactory;\n", "")
                .replace("import org.springframework.batch.core.configuration.annotation.StepBuilderFactory;\n", "");
        List<String> imports = new ArrayList<>();
        imports.add("org.springframework.batch.core.repository.JobRepository");
        if (job) imports.add("org.springframework.batch.core.job.builder.JobBuilder");
        if (step) imports.add("org.springframework.batch.core.step.builder.StepBuilder");
        for (String fqcn : imports) result = ensureImport(result, fqcn);
        return result;
    }

    private static String ensureImport(String source, String fqcn) {
        if (source.contains("import " + fqcn + ";")) return source;
        int packageEnd = source.indexOf(';', source.indexOf("package "));
        if (packageEnd >= 0) {
            return source.substring(0, packageEnd + 1) + "\n\nimport " + fqcn + ";" + source.substring(packageEnd + 1);
        }
        return "import " + fqcn + ";\n" + source;
    }

    private static String apply(String source, List<Edit> edits) {
        StringBuilder result = new StringBuilder(source);
        edits.stream().sorted(Comparator.comparingLong(Edit::start).reversed()).forEach(edit ->
                result.replace(Math.toIntExact(edit.start), Math.toIntExact(edit.end), edit.replacement));
        return result.toString();
    }

    private static String relative(Path root, Path file) {
        return root.relativize(file).toString().replace('\\', '/');
    }

    record FileRewrite(String source, List<String> rules, List<String> blockers) {}
    private record Edit(long start, long end, String replacement) {}

    private static final class Scanner extends TreePathScanner<Void, Void> {
        private final String source;
        private final CompilationUnitTree unit;
        private final SourcePositions positions;
        private final List<Edit> edits = new ArrayList<>();
        private final List<String> blockers = new ArrayList<>();
        private final Set<String> jobFactories = new LinkedHashSet<>();
        private final Set<String> stepFactories = new LinkedHashSet<>();
        private boolean jobFactorySeen;
        private boolean stepFactorySeen;
        private boolean hasTransactionManager;
        private boolean needsTransactionManager;

        private Scanner(String source, CompilationUnitTree unit, SourcePositions positions) {
            this.source = source;
            this.unit = unit;
            this.positions = positions;
        }

        @Override public Void visitVariable(VariableTree node, Void unused) {
            String type = node.getType().toString();
            if (type.endsWith("JobBuilderFactory")) {
                jobFactorySeen = true;
                jobFactories.add(node.getName().toString());
                replace(node.getType(), "JobRepository");
            } else if (type.endsWith("StepBuilderFactory")) {
                stepFactorySeen = true;
                stepFactories.add(node.getName().toString());
                replace(node.getType(), "JobRepository");
            } else if (type.endsWith("PlatformTransactionManager")) {
                hasTransactionManager = true;
            }
            return super.visitVariable(node, unused);
        }

        @Override public Void visitMethodInvocation(MethodInvocationTree node, Void unused) {
            if (node.getMethodSelect() instanceof MemberSelectTree select) {
                String receiver = select.getExpression().toString();
                if (select.getIdentifier().contentEquals("get") && node.getArguments().size() == 1) {
                    if (jobFactories.contains(receiver)) {
                        replace(node, "new JobBuilder(" + text(node.getArguments().get(0)) + ", " + receiver + ")");
                    } else if (stepFactories.contains(receiver)) {
                        replace(node, "new StepBuilder(" + text(node.getArguments().get(0)) + ", " + receiver + ")");
                    }
                }
                if (select.getIdentifier().contentEquals("chunk") && node.getArguments().size() == 1
                        && (receiver.contains("StepBuilder") || stepFactories.stream().anyMatch(receiver::contains))) {
                    needsTransactionManager = true;
                    String methodSelect = text(node.getMethodSelect());
                    if (select.getExpression() instanceof MethodInvocationTree nested
                            && nested.getMethodSelect() instanceof MemberSelectTree nestedSelect
                            && nestedSelect.getIdentifier().contentEquals("get")
                            && stepFactories.contains(nestedSelect.getExpression().toString())
                            && nested.getArguments().size() == 1) {
                        String oldReceiver = text(nested);
                        String newReceiver = "new StepBuilder(" + text(nested.getArguments().get(0)) + ", "
                                + nestedSelect.getExpression() + ")";
                        methodSelect = methodSelect.replace(oldReceiver, newReceiver);
                    }
                    replace(node, methodSelect + "(" + text(node.getArguments().get(0))
                            + ", transactionManager)");
                }
            }
            return super.visitMethodInvocation(node, unused);
        }

        private String text(Tree tree) {
            long start = positions.getStartPosition(unit, tree);
            long end = positions.getEndPosition(unit, tree);
            return start < 0 || end < start ? tree.toString() : source.substring((int) start, (int) end);
        }

        private void replace(Tree tree, String replacement) {
            long start = positions.getStartPosition(unit, tree);
            long end = positions.getEndPosition(unit, tree);
            if (start < 0 || end < start) blockers.add("AST source position unavailable for " + tree.getKind());
            else if (edits.stream().noneMatch(edit -> edit.start <= start && edit.end >= end)) {
                edits.add(new Edit(start, end, replacement));
            }
        }
    }

    private static final class SourceFile extends SimpleJavaFileObject {
        private final String source;
        private SourceFile(String name, String source) {
            super(URI.create("string:///" + name.replace('\\', '/')), Kind.SOURCE);
            this.source = source;
        }
        @Override public CharSequence getCharContent(boolean ignoreEncodingErrors) { return source; }
    }
}
