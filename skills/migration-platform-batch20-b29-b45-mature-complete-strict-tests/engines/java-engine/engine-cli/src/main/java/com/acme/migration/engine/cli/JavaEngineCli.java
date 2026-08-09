package com.acme.migration.engine.cli;

import com.acme.migration.engine.api.PspDocument;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class JavaEngineCli {
    private static final Pattern PACKAGE = Pattern.compile("\\bpackage\\s+([\\w.]+)\\s*;");
    private static final Pattern TYPE = Pattern.compile("\\b(?:class|interface|record|enum)\\s+(\\w+)");

    private JavaEngineCli() {}

    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            System.err.println("Usage: java-engine-cli <repository-path> <output-psp.json>");
            System.exit(2);
        }
        Path repository = Path.of(args[0]).toAbsolutePath().normalize();
        Path output = Path.of(args[1]).toAbsolutePath().normalize();
        PspDocument document = analyze(repository);
        Files.createDirectories(output.getParent());
        Files.writeString(output, toJson(document));
        System.out.printf("Wrote PSP %s with %d Java files%n", output, document.sourceFileCount());
    }

    public static PspDocument analyze(Path repository) throws IOException {
        if (!Files.isDirectory(repository)) throw new IllegalArgumentException("repository path is not a directory");
        var units = new ArrayList<PspDocument.SourceUnit>();
        var packages = new LinkedHashSet<String>();
        try (var paths = Files.walk(repository)) {
            for (Path path : paths.filter(p -> p.toString().endsWith(".java")).sorted().toList()) {
                String source = Files.readString(path);
                String packageName = match(PACKAGE, source);
                if (!packageName.isBlank()) packages.add(packageName);
                List<String> types = matches(TYPE, source);
                units.add(new PspDocument.SourceUnit(
                        repository.relativize(path).toString().replace('\\', '/'), packageName, types));
            }
        }
        return new PspDocument("psp/0.1", "java", Instant.now(), repository.toString(),
                units.size(), List.copyOf(packages), List.copyOf(units));
    }

    static String toJson(PspDocument document) {
        StringBuilder json = new StringBuilder();
        json.append("{\n");
        field(json, "schemaVersion", document.schemaVersion(), true, 1);
        field(json, "language", document.language(), true, 1);
        field(json, "generatedAt", document.generatedAt().toString(), true, 1);
        field(json, "repository", document.repository(), true, 1);
        json.append("  \"sourceFileCount\": ").append(document.sourceFileCount()).append(",\n");
        json.append("  \"packages\": ");
        stringArray(json, document.packages());
        json.append(",\n  \"sourceUnits\": [\n");
        for (int i = 0; i < document.sourceUnits().size(); i++) {
            var unit = document.sourceUnits().get(i);
            json.append("    {\n");
            field(json, "path", unit.path(), true, 3);
            field(json, "packageName", unit.packageName(), true, 3);
            json.append("      \"declaredTypes\": ");
            stringArray(json, unit.declaredTypes());
            json.append("\n    }");
            if (i + 1 < document.sourceUnits().size()) json.append(',');
            json.append('\n');
        }
        json.append("  ]\n}\n");
        return json.toString();
    }

    private static void field(StringBuilder json, String name, String value, boolean comma, int indent) {
        json.append("  ".repeat(indent)).append('"').append(escape(name)).append("\": \"")
                .append(escape(value)).append('"');
        if (comma) json.append(',');
        json.append('\n');
    }

    private static void stringArray(StringBuilder json, List<String> values) {
        json.append('[');
        for (int i = 0; i < values.size(); i++) {
            if (i > 0) json.append(", ");
            json.append('"').append(escape(values.get(i))).append('"');
        }
        json.append(']');
    }

    private static String escape(String value) {
        return value.replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t");
    }

    private static String match(Pattern pattern, String text) {
        Matcher matcher = pattern.matcher(text);
        return matcher.find() ? matcher.group(1) : "";
    }

    private static List<String> matches(Pattern pattern, String text) {
        List<String> values = new ArrayList<>();
        Matcher matcher = pattern.matcher(text);
        while (matcher.find()) values.add(matcher.group(1));
        return values;
    }
}
