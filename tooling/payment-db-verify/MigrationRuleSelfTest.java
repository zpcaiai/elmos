import java.io.IOException;
import java.nio.file.*;
import java.util.*;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

/** 复刻打补丁后的断言逻辑，在合成目录上验证它挡得住什么、放得过什么。 */
public final class MigrationRuleSelfTest {
    private static int passed, failed;

    /** 返回 null 表示通过；否则返回失败原因。逻辑与测试方法逐行一致。 */
    static String evaluate(Path migrations) throws IOException {
        List<String> fileNames;
        try (var files = Files.list(migrations)) {
            fileNames = files.map(p -> p.getFileName().toString())
                    .filter(n -> n.matches("V\\d+__.+\\.sql")).toList();
        }
        List<Integer> versions = fileNames.stream()
                .map(n -> Integer.parseInt(n.replaceFirst("^V", "").replaceFirst("__.*", "")))
                .toList();
        Set<Integer> unique = Set.copyOf(versions);
        if (versions.size() != unique.size()) return "重复版本号";
        int highest = unique.stream().mapToInt(Integer::intValue).max().orElseThrow();
        Set<Integer> expected = IntStream.rangeClosed(1, highest).boxed()
                .collect(Collectors.toSet());
        if (!expected.equals(unique)) {
            Set<Integer> missing = new TreeSet<>(expected); missing.removeAll(unique);
            Set<Integer> extra = new TreeSet<>(unique); extra.removeAll(expected);
            return "缺号=" + missing + " 多余=" + extra;
        }
        return null;
    }

    static Path scenario(String name, int[] versions, String... extraFiles) throws IOException {
        Path dir = Files.createTempDirectory("mig-" + name);
        for (int v : versions) Files.writeString(dir.resolve("V" + v + "__x.sql"), "-- x");
        for (String f : extraFiles) Files.writeString(dir.resolve(f), "-- x");
        return dir;
    }

    public static void main(String[] args) throws Exception {
        int[] current = IntStream.rangeClosed(1, 63).toArray();

        check("当前真实版本集（V1–V63，严格连续）应通过",
                evaluate(scenario("cur", current)) == null);

        int[] lowerContiguous = IntStream.rangeClosed(1, 54).toArray();
        check("较低但连续的 V1–V54 也通过（上限自适应）",
                evaluate(scenario("lower", lowerContiguous)) == null);

        int[] gap = Arrays.stream(current).filter(v -> v != 30).toArray();
        String r = evaluate(scenario("gap", gap));
        check("意外删掉 V30 -> 仍然失败（守卫没被削弱）: " + r, r != null && r.contains("30"));

        String r2 = evaluate(scenario("dup", current, "V30__another.sql"));
        check("同一版本号出现两次 -> 失败: " + r2, "重复版本号".equals(r2));

        int[] missingV52 = Arrays.stream(current).filter(v -> v != 52).toArray();
        String r3 = evaluate(scenario("missing52", missingV52));
        check("V52 被删除 -> 失败: " + r3, r3 != null && r3.contains("52"));

        int[] next = Arrays.copyOf(current, current.length + 1);
        next[current.length] = 64;
        check("正常新增 V64 -> 通过（不必再改测试）",
                evaluate(scenario("next", next)) == null);

        int[] twoGaps = Arrays.stream(next).filter(v -> v != 40 && v != 41).toArray();
        String r4 = evaluate(scenario("twogaps", twoGaps));
        check("连续两个缺号 -> 失败: " + r4, r4 != null && r4.contains("40") && r4.contains("41"));

        System.out.printf("%n结果：%d 通过，%d 失败%n", passed, failed);
        if (failed > 0) System.exit(1);
    }

    static void check(String n, boolean ok) {
        if (ok) { passed++; System.out.println("  [PASS] " + n); }
        else { failed++; System.out.println("  [FAIL] " + n); }
    }
}
