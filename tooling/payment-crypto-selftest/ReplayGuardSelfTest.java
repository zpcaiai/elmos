import io.elmos.commercialadapter.payment.CallbackReplayGuard;
import io.elmos.commercialadapter.payment.CallbackReplayGuard.Verdict;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

/** 回调时间戳偏差校验。重点是两个方向都要卡，以及边界的开闭。 */
public final class ReplayGuardSelfTest {
    private static int passed, failed;

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-09-01T12:00:00Z");
        Clock fixed = Clock.fixed(now, ZoneOffset.UTC);
        CallbackReplayGuard guard = new CallbackReplayGuard(fixed);

        section("时间窗（容差 5 分钟）");
        check("当前时刻通过", guard.check(now) == Verdict.ACCEPTED);
        check("4 分 59 秒前通过", guard.check(now.minusSeconds(299)) == Verdict.ACCEPTED);
        check("整 5 分钟前通过（边界闭区间）", guard.check(now.minusSeconds(300)) == Verdict.ACCEPTED);
        check("5 分 01 秒前 -> TOO_OLD", guard.check(now.minusSeconds(301)) == Verdict.TOO_OLD);
        check("1 小时前 -> TOO_OLD（典型重放）", guard.check(now.minusSeconds(3600)) == Verdict.TOO_OLD);
        check("整 5 分钟后通过", guard.check(now.plusSeconds(300)) == Verdict.ACCEPTED);
        check("5 分 01 秒后 -> TOO_NEW（时钟不同步或报文被构造）",
                guard.check(now.plusSeconds(301)) == Verdict.TOO_NEW);
        check("一年后 -> TOO_NEW", guard.check(now.plusSeconds(31536000)) == Verdict.TOO_NEW);

        section("微信 Wechatpay-Timestamp（Unix 秒字符串）");
        long epoch = now.getEpochSecond();
        check("当前时间戳通过", guard.accepts(Long.toString(epoch)));
        check("带空白仍可解析", guard.accepts(" " + epoch + " "));
        check("1 小时前 -> 拒绝", !guard.accepts(Long.toString(epoch - 3600)));
        check("1 小时后 -> 拒绝", !guard.accepts(Long.toString(epoch + 3600)));

        section("畸形输入一律 MALFORMED（不抛异常）");
        for (String bad : new String[] {null, "", "abc", "12.5", "1e9", "-1", "0",
                                        "99999999999999999999"}) {
            check("拒绝 " + (bad == null ? "null" : "\"" + bad + "\""),
                    guard.checkUnixSeconds(bad) == Verdict.MALFORMED);
        }
        check("毫秒被当成秒会落到极远未来 -> 不是 ACCEPTED",
                guard.checkUnixSeconds(Long.toString(epoch * 1000)) != Verdict.ACCEPTED);

        section("容差本身受约束");
        check("容差为 0 -> 构造即拒绝",
                throwsIllegalArgument(() -> new CallbackReplayGuard(fixed, Duration.ZERO)));
        check("负容差 -> 构造即拒绝",
                throwsIllegalArgument(() -> new CallbackReplayGuard(fixed, Duration.ofMinutes(-1))));
        check("容差超过 1 小时 -> 拒绝（容差就是重放窗口）",
                throwsIllegalArgument(() -> new CallbackReplayGuard(fixed, Duration.ofHours(2))));
        check("clock 未注入 -> 拒绝",
                throwsIllegalArgument(() -> new CallbackReplayGuard(null)));
        check("默认容差为 5 分钟", guard.tolerance().equals(Duration.ofMinutes(5)));

        section("与幂等的关系");
        CallbackReplayGuard tight = new CallbackReplayGuard(fixed, Duration.ofSeconds(30));
        check("窗口收紧后 1 分钟前的报文被拒（时间窗独立于幂等台账生效）",
                tight.check(now.minusSeconds(60)) == Verdict.TOO_OLD);
        check("窗口内的重复仍需幂等台账兜住（时间窗本身放行）",
                tight.check(now.minusSeconds(10)) == Verdict.ACCEPTED);

        System.out.printf("%n结果：%d 通过，%d 失败%n", passed, failed);
        if (failed > 0) System.exit(1);
    }

    private interface Block { void run() throws Exception; }
    private static boolean throwsIllegalArgument(Block b) {
        try { b.run(); return false; }
        catch (IllegalArgumentException e) { return true; }
        catch (Exception e) { return false; }
    }
    private static void section(String t) { System.out.println(); System.out.println("== " + t + " =="); }
    private static void check(String n, boolean ok) {
        if (ok) { passed++; System.out.println("  [PASS] " + n); }
        else { failed++; System.out.println("  [FAIL] " + n); }
    }
}
