import io.elmos.commercial.PricingPlanCatalog;
import java.math.BigDecimal;
import java.util.List;

/** PricingPlanCatalogTest 新增断言的等价校验（本环境没有 JUnit，用同样的判据先跑一遍）。 */
public final class CatalogContractSelfTest {
    private static int passed, failed;
    public static void main(String[] a) {
        var c = PricingPlanCatalog.chinaSelfServeDraft();
        check("paymentProvider 在契约取值域内",
            List.of("STRIPE_CHECKOUT","ALIPAY_CHECKOUT","WECHAT_PAY_NATIVE").contains(c.paymentProvider()));
        check("currency = CNY", "CNY".equals(c.currency()));
        check("CNY 下不是 STRIPE_CHECKOUT", !"STRIPE_CHECKOUT".equals(c.paymentProvider()));
        check("试用 14 天", PricingPlanCatalog.requirePlan("elmos-free-trial").termDays()==14);
        check("月付 31 天", PricingPlanCatalog.requirePlan("elmos-pro-monthly").termDays()==31);
        check("年付 365 天", PricingPlanCatalog.requirePlan("elmos-pro-annual").termDays()==365);
        check("129.00 元 == 12900 分",
            new BigDecimal("129.00").movePointRight(2).compareTo(new BigDecimal(12900))==0);
        check("月付价 129.00", new BigDecimal("129.00").equals(
            PricingPlanCatalog.requirePlan("elmos-pro-monthly").price().amount()));
        check("年付价 1290.00", new BigDecimal("1290.00").equals(
            PricingPlanCatalog.requirePlan("elmos-pro-annual").price().amount()));
        check("paymentStatus 仍是 NOT_CONFIGURED", "NOT_CONFIGURED".equals(c.paymentStatus()));
        check("sellerLegalEntityStatus 仍是 NOT_CONFIGURED", "NOT_CONFIGURED".equals(c.sellerLegalEntityStatus()));
        boolean threw=false;
        try { PricingPlanCatalog.requireOrderable(); } catch (IllegalStateException e) { threw=true; }
        check("requireOrderable 仍然拒绝", threw);
        System.out.println("\n结果：" + passed + " 通过，" + failed + " 失败");
        if (failed>0) System.exit(1);
    }
    private static void check(String w, boolean ok){ if(ok){passed++;System.out.println("  [PASS] "+w);} else {failed++;System.out.println("  [FAIL] "+w);} }
}
