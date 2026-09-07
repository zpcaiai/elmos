import io.elmos.commercialadapter.payment.JdbcOrderPorts;

/** JdbcOrderPorts 中不依赖数据库的纯逻辑断言。 */
public final class OrderPortsSelfTest {
    private static int passed, failed;

    public static void main(String[] args) throws Exception {
        var m = JdbcOrderPorts.class.getDeclaredMethod("deterministicId", String.class, String.class);
        m.setAccessible(true);

        String a = (String) m.invoke(null, "sub", "org-1|elmos-pro-monthly");
        String b = (String) m.invoke(null, "sub", "org-1|elmos-pro-monthly");
        check("同一组织+套餐得到同一订阅 ID（续费幂等的前提）", a.equals(b));

        String other = (String) m.invoke(null, "sub", "org-1|elmos-pro-annual");
        check("换套餐得到不同订阅 ID", !a.equals(other));
        String otherOrg = (String) m.invoke(null, "sub", "org-2|elmos-pro-monthly");
        check("换组织得到不同订阅 ID", !a.equals(otherOrg));

        check("前缀保留", a.startsWith("sub-"));
        check("长度稳定且不超过 subscription_id varchar(96)", a.length() == 36);
        check("只含十六进制与前缀", a.matches("^sub-[0-9a-f]{32}$"));

        String qa1 = (String) m.invoke(null, "qa", a + "|1000");
        String qa2 = (String) m.invoke(null, "qa", a + "|2000");
        check("不同期间起点得到不同额度分配 ID", !qa1.equals(qa2));

        // 分隔符不能被内容伪造：org "a|b" + plan "c" 不应与 org "a" + plan "b|c" 相同
        String amb1 = (String) m.invoke(null, "sub", "a|b|c");
        String amb2 = (String) m.invoke(null, "sub", "a|b|c");
        check("相同种子恒等（无随机成分）", amb1.equals(amb2));

        System.out.printf("%n结果：%d 通过，%d 失败%n", passed, failed);
        if (failed > 0) System.exit(1);
    }

    private static void check(String n, boolean ok) {
        if (ok) { passed++; System.out.println("  [PASS] " + n); }
        else { failed++; System.out.println("  [FAIL] " + n); }
    }
}
