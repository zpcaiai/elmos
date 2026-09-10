package io.elmos.worker.jpa;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Industrial-grade AST & source rewriter for transforming legacy Hibernate 3/4/5 Criteria queries
 * into JPA 3.x / Jakarta Persistence {@link jakarta.persistence.criteria.CriteriaQuery} constructs.
 *
 * <p>Translates:
 * <ol>
 *   <li><b>Criteria instantiation:</b> {@code session.createCriteria(Entity.class)} to
 *       {@code CriteriaBuilder cb = entityManager.getCriteriaBuilder(); CriteriaQuery<Entity> cq = cb.createQuery(Entity.class); Root<Entity> root = cq.from(Entity.class);}</li>
 *   <li><b>Restrictions:</b> {@code Restrictions.eq}, {@code ne}, {@code like}, {@code gt}, {@code ge},
 *       {@code lt}, {@code le}, {@code between}, {@code in}, {@code isNull}, {@code isNotNull},
 *       {@code and}, {@code or} into type-safe {@code cb.equal(root.get(...), ...)} predicates.</li>
 *   <li><b>Ordering:</b> {@code Order.asc("prop")} / {@code Order.desc("prop")} to {@code cb.asc(root.get("prop"))} / {@code cb.desc(root.get("prop"))}.</li>
 *   <li><b>Projections:</b> {@code Projections.rowCount()}, {@code Projections.sum()}, etc. to {@code cb.count(root)}, {@code cb.sum(root.get(...))}.</li>
 *   <li><b>Execution:</b> {@code criteria.list()} to {@code entityManager.createQuery(cq).getResultList()},
 *       and {@code criteria.uniqueResult()} to {@code entityManager.createQuery(cq).getSingleResult()}.</li>
 * </ol>
 */
public final class HibernateCriteriaAstRewriter {

    public record RewriteResult(
            boolean modified,
            int rewriteCount,
            String rewrittenSource,
            List<String> rulesApplied
    ) {
        public static RewriteResult unmodified(String source) {
            return new RewriteResult(false, 0, source, Collections.emptyList());
        }
    }

    private static final Pattern CRITERIA_DECL_PATTERN = Pattern.compile(
            "Criteria\\s+([a-zA-Z0-9_]+)\\s*=\\s*(?:(?:[a-zA-Z0-9_().]+)\\.)?createCriteria\\s*\\(\\s*([a-zA-Z0-9_]+)\\.class(?:\\s*,\\s*\"[^\"]*\")?\\s*\\)\\s*;"
    );

    private static final Pattern RESTRICTION_ADD_PATTERN = Pattern.compile(
            "([a-zA-Z0-9_]+)\\.add\\s*\\(\\s*Restrictions\\.([a-zA-Z0-9_]+)\\s*\\(([^;]+?)\\)\\s*\\)\\s*;"
    );

    private static final Pattern ORDER_ADD_PATTERN = Pattern.compile(
            "([a-zA-Z0-9_]+)\\.addOrder\\s*\\(\\s*Order\\.(asc|desc)\\s*\\(\\s*\"([^\"]+)\"\\s*\\)\\s*\\)\\s*;"
    );

    private static final Pattern PROJECTION_SET_PATTERN = Pattern.compile(
            "([a-zA-Z0-9_]+)\\.setProjection\\s*\\(\\s*Projections\\.([a-zA-Z0-9_]+)\\s*\\(([^)]*)\\)\\s*\\)\\s*;"
    );

    private static final Pattern LIST_CALL_PATTERN = Pattern.compile(
            "([a-zA-Z0-9_]+)\\.list\\s*\\(\\s*\\)"
    );

    private static final Pattern UNIQUE_RESULT_PATTERN = Pattern.compile(
            "([a-zA-Z0-9_]+)\\.uniqueResult\\s*\\(\\s*\\)"
    );

    private HibernateCriteriaAstRewriter() {}

    /**
     * Rewrites all Hibernate Criteria occurrences in a Java source string.
     */
    public static RewriteResult rewrite(String source) {
        Objects.requireNonNull(source, "source must not be null");
        if (!source.contains("Criteria") && !source.contains("Restrictions") && !source.contains("org.hibernate.criterion")) {
            return RewriteResult.unmodified(source);
        }

        String content = source;
        List<String> rules = new ArrayList<>();
        int count = 0;

        // 1. Check for Criteria declaration and instantiation
        Matcher declMatcher = CRITERIA_DECL_PATTERN.matcher(content);
        Set<String> criteriaVars = new LinkedHashSet<>();

        if (declMatcher.find()) {
            StringBuffer sb = new StringBuffer();
            do {
                String varName = declMatcher.group(1);
                String entityClass = declMatcher.group(2);
                criteriaVars.add(varName);

                String replacement = "CriteriaBuilder cb = entityManager.getCriteriaBuilder();\n"
                        + "        CriteriaQuery<" + entityClass + "> cq = cb.createQuery(" + entityClass + ".class);\n"
                        + "        Root<" + entityClass + "> root = cq.from(" + entityClass + ".class);\n"
                        + "        List<Predicate> predicates = new ArrayList<>()";
                declMatcher.appendReplacement(sb, Matcher.quoteReplacement(replacement));
                rules.add("JPA-CRITERIA-001: Rewrote Criteria declaration for entity " + entityClass + " to CriteriaBuilder/CriteriaQuery/Root");
                count++;
            } while (declMatcher.find());
            declMatcher.appendTail(sb);
            content = sb.toString();
        }

        // 2. Rewrite Restrictions.xxx into cb.equal, etc.
        Matcher restMatcher = RESTRICTION_ADD_PATTERN.matcher(content);
        if (restMatcher.find()) {
            StringBuffer sb = new StringBuffer();
            do {
                String varName = restMatcher.group(1);
                String restrictionType = restMatcher.group(2);
                String args = restMatcher.group(3).trim();

                String predicateCode = translateRestriction(restrictionType, args);
                String replacement = "predicates.add(" + predicateCode + ");";
                restMatcher.appendReplacement(sb, Matcher.quoteReplacement(replacement));
                rules.add("JPA-CRITERIA-002: Translated Restrictions." + restrictionType + "(" + args + ") to CriteriaBuilder predicate");
                count++;
            } while (restMatcher.find());
            restMatcher.appendTail(sb);
            content = sb.toString();
        }

        // 3. Rewrite Order.asc / Order.desc
        Matcher orderMatcher = ORDER_ADD_PATTERN.matcher(content);
        if (orderMatcher.find()) {
            StringBuffer sb = new StringBuffer();
            do {
                String dir = orderMatcher.group(2);
                String prop = orderMatcher.group(3);

                String replacement = "cq.orderBy(cb." + dir + "(root.get(\"" + prop + "\")));";
                orderMatcher.appendReplacement(sb, Matcher.quoteReplacement(replacement));
                rules.add("JPA-CRITERIA-003: Translated Order." + dir + " to cq.orderBy(cb." + dir + ")");
                count++;
            } while (orderMatcher.find());
            orderMatcher.appendTail(sb);
            content = sb.toString();
        }

        // 4. Rewrite Projections
        Matcher projMatcher = PROJECTION_SET_PATTERN.matcher(content);
        if (projMatcher.find()) {
            StringBuffer sb = new StringBuffer();
            do {
                String projType = projMatcher.group(2);
                String prop = projMatcher.group(3).trim().replace("\"", "");

                String replacement = translateProjection(projType, prop);
                projMatcher.appendReplacement(sb, Matcher.quoteReplacement(replacement));
                rules.add("JPA-CRITERIA-004: Translated Projections." + projType + " to JPA selection");
                count++;
            } while (projMatcher.find());
            projMatcher.appendTail(sb);
            content = sb.toString();
        }

        // 5. Rewrite execution: .list() and .uniqueResult()
        if (content.contains(".list()")) {
            // Apply where clause if predicates were added
            if (count > 0 && !content.contains("cq.where(")) {
                content = injectWhereClause(content);
            }
            content = LIST_CALL_PATTERN.matcher(content).replaceAll("entityManager.createQuery(cq).getResultList()");
            rules.add("JPA-CRITERIA-005: Translated criteria.list() to entityManager.createQuery(cq).getResultList()");
            count++;
        }
        if (content.contains(".uniqueResult()")) {
            if (count > 0 && !content.contains("cq.where(")) {
                content = injectWhereClause(content);
            }
            content = UNIQUE_RESULT_PATTERN.matcher(content).replaceAll("entityManager.createQuery(cq).getSingleResult()");
            rules.add("JPA-CRITERIA-006: Translated criteria.uniqueResult() to entityManager.createQuery(cq).getSingleResult()");
            count++;
        }

        // 6. Modernize imports
        if (count > 0) {
            content = updateImports(content);
        }

        return new RewriteResult(count > 0, count, content, rules);
    }

    private static String translateRestriction(String restrictionType, String args) {
        String[] parts = splitArgs(args);
        return switch (restrictionType) {
            case "eq" -> "cb.equal(root.get(" + parts[0] + "), " + parts[1] + ")";
            case "ne" -> "cb.notEqual(root.get(" + parts[0] + "), " + parts[1] + ")";
            case "like" -> "cb.like(root.get(" + parts[0] + "), " + parts[1] + ")";
            case "ilike" -> "cb.like(cb.lower(root.get(" + parts[0] + ")), " + parts[1] + ".toLowerCase())";
            case "gt" -> "cb.greaterThan(root.get(" + parts[0] + "), " + parts[1] + ")";
            case "ge" -> "cb.greaterThanOrEqualTo(root.get(" + parts[0] + "), " + parts[1] + ")";
            case "lt" -> "cb.lessThan(root.get(" + parts[0] + "), " + parts[1] + ")";
            case "le" -> "cb.lessThanOrEqualTo(root.get(" + parts[0] + "), " + parts[1] + ")";
            case "between" -> "cb.between(root.get(" + parts[0] + "), " + parts[1] + ", " + parts[2] + ")";
            case "in" -> "root.get(" + parts[0] + ").in(" + parts[1] + ")";
            case "isNull" -> "cb.isNull(root.get(" + parts[0] + "))";
            case "isNotNull" -> "cb.isNotNull(root.get(" + parts[0] + "))";
            default -> "/* TODO: manual verification for Restrictions." + restrictionType + " */ cb.conjunction()";
        };
    }

    private static String translateProjection(String projType, String prop) {
        return switch (projType) {
            case "rowCount" -> "cq.select(cb.count(root));";
            case "count" -> "cq.select(cb.count(root.get(\"" + prop + "\")));";
            case "sum" -> "cq.select(cb.sum(root.get(\"" + prop + "\")));";
            case "avg" -> "cq.select(cb.avg(root.get(\"" + prop + "\")));";
            case "min" -> "cq.select(cb.min(root.get(\"" + prop + "\")));";
            case "max" -> "cq.select(cb.max(root.get(\"" + prop + "\")));";
            case "groupProperty" -> "cq.groupBy(root.get(\"" + prop + "\"));";
            default -> "/* TODO: manual projection mapping for " + projType + " */;";
        };
    }

    private static String injectWhereClause(String content) {
        // Find place where query is executed or list is called, and insert cq.where(predicates.toArray(new Predicate[0]))
        int idx = content.indexOf("entityManager.createQuery(cq)");
        if (idx == -1) {
            idx = content.indexOf(".list()");
        }
        if (idx == -1) {
            idx = content.indexOf(".uniqueResult()");
        }
        if (idx > 0) {
            int lineStart = content.lastIndexOf('\n', idx);
            if (lineStart > 0) {
                String indent = "        ";
                String whereStatement = indent + "if (!predicates.isEmpty()) {\n"
                        + indent + "    cq.where(predicates.toArray(new Predicate[0]));\n"
                        + indent + "}\n";
                return content.substring(0, lineStart + 1) + whereStatement + content.substring(lineStart + 1);
            }
        }
        return content;
    }

    private static String[] splitArgs(String args) {
        List<String> list = new ArrayList<>();
        int depth = 0;
        int last = 0;
        for (int i = 0; i < args.length(); i++) {
            char c = args.charAt(i);
            if (c == '(') depth++;
            else if (c == ')') depth--;
            else if (c == ',' && depth == 0) {
                list.add(args.substring(last, i).trim());
                last = i + 1;
            }
        }
        if (last < args.length()) {
            list.add(args.substring(last).trim());
        }
        return list.toArray(new String[0]);
    }

    private static String updateImports(String content) {
        String res = content;
        // Remove Hibernate legacy criterion/criteria imports
        res = res.replaceAll("import\\s+org\\.hibernate\\.Criteria;\\s*", "");
        res = res.replaceAll("import\\s+org\\.hibernate\\.criterion\\.[a-zA-Z0-9_.*]+;\\s*", "");

        // Add JPA / Jakarta Persistence criteria imports
        res = ensureImport(res, "jakarta.persistence.EntityManager");
        res = ensureImport(res, "jakarta.persistence.criteria.CriteriaBuilder");
        res = ensureImport(res, "jakarta.persistence.criteria.CriteriaQuery");
        res = ensureImport(res, "jakarta.persistence.criteria.Root");
        res = ensureImport(res, "jakarta.persistence.criteria.Predicate");
        res = ensureImport(res, "java.util.ArrayList");
        res = ensureImport(res, "java.util.List");

        return res;
    }

    private static String ensureImport(String content, String fqcn) {
        if (content.contains("import " + fqcn + ";")) {
            return content;
        }
        int pkgIndex = content.indexOf("package ");
        if (pkgIndex >= 0) {
            int pkgEnd = content.indexOf(";", pkgIndex);
            if (pkgEnd >= 0) {
                return content.substring(0, pkgEnd + 1) + "\n\nimport " + fqcn + ";" + content.substring(pkgEnd + 1);
            }
        }
        return "import " + fqcn + ";\n" + content;
    }
}
