import io.elmos.commercialadapter.payment.JdbcCallbackPorts;

/** JdbcCallbackPorts 中不依赖数据库的纯逻辑断言。 */
public final class JdbcPortsSelfTest {
    private static int passed, failed;

    public static void main(String[] args) throws Exception {
        var split = JdbcCallbackPorts.class.getDeclaredMethod("splitKey", String.class);
        split.setAccessible(true);
        var sha = JdbcCallbackPorts.class.getDeclaredMethod("sha256Hex", String.class);
        sha.setAccessible(true);

        String[] parts = (String[]) split.invoke(null, "ALIPAY_CHECKOUT:evt-1");
        check("幂等键切分：通道", "ALIPAY_CHECKOUT".equals(parts[0]));
        check("幂等键切分：事件 ID", "evt-1".equals(parts[1]));

        String[] withColon = (String[]) split.invoke(null, "WECHAT_PAY_NATIVE:evt:with:colons");
        check("事件 ID 含冒号时只切第一个", "evt:with:colons".equals(withColon[1]));

        for (String bad : new String[] {":evt", "PROVIDER:", "noseparator"}) {
            boolean threw = false;
            try { split.invoke(null, bad); } catch (Exception e) { threw = true; }
            check("非法幂等键被拒: " + bad, threw);
        }
        boolean nullThrew = false;
        try { split.invoke(null, (Object) null); } catch (Exception e) { nullThrew = true; }
        check("null 幂等键被拒", nullThrew);

        String hex = (String) sha.invoke(null, "{}");
        check("sha256 输出 64 位小写十六进制", hex.matches("^[0-9a-f]{64}$"));
        check("sha256 与已知值一致（空对象 {}）",
            "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a".equals(hex));
        check("null 与空串摘要一致（不抛异常）",
            sha.invoke(null, (Object) null).equals(sha.invoke(null, "")));

        System.out.printf("%n结果：%d 通过，%d 失败%n", passed, failed);
        if (failed > 0) System.exit(1);
    }

    private static void check(String name, boolean ok) {
        if (ok) { passed++; System.out.println("  [PASS] " + name); }
        else { failed++; System.out.println("  [FAIL] " + name); }
    }
}
