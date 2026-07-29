package io.elmos.commercialadapter.payment;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

/**
 * 回调时间戳偏差校验。
 *
 * <p><b>验签不防重放。</b>攻击者截获一个合法回调后原样重发，签名依然有效。
 * 幂等台账能挡住同一个提供方事件 ID 的重复，但挡不住这两种情况：
 *
 * <ul>
 *   <li>台账被清理（保留期到期）之后的旧回调重放</li>
 *   <li>提供方事件 ID 可被攻击者控制或猜测的场景</li>
 * </ul>
 *
 * <p>因此时间窗校验是幂等之外的独立一道，两者<b>不能互相替代</b>：
 * 时间窗挡住陈旧报文，幂等挡住窗口内的重复。
 *
 * <h2>为什么两个方向都要卡</h2>
 *
 * <p>过旧要拒，很直观。<b>过新同样要拒</b>：时间戳落在未来意味着
 * 我们的时钟慢了、对方时钟快了，或者报文被构造过。放行未来时间戳等于
 * 把重放窗口延长到"未来那一刻 + 容差"，攻击者只要把时间戳往后写就能延长有效期。
 *
 * <p>容差取 5 分钟：支付宝与微信的官方建议量级一致，
 * 也足够覆盖正常的 NTP 漂移。这个值不应为了"少报错"而放大——
 * 放大它就是直接放大重放窗口。
 */
public final class CallbackReplayGuard {

    /** 默认容差。两个方向各 5 分钟。 */
    public static final Duration DEFAULT_TOLERANCE = Duration.ofMinutes(5);

    /** 判定结果。除 {@link #ACCEPTED} 外都必须拒绝回调。 */
    public enum Verdict {
        ACCEPTED,
        /** 时间戳早于容差窗口 —— 陈旧报文，典型的重放。 */
        TOO_OLD,
        /** 时间戳晚于容差窗口 —— 时钟不同步或报文被构造。 */
        TOO_NEW,
        /** 缺失、非数字、超出合理范围。 */
        MALFORMED
    }

    private final Clock clock;
    private final Duration tolerance;

    public CallbackReplayGuard(Clock clock, Duration tolerance) {
        if (clock == null) {
            throw new IllegalArgumentException("clock 未注入");
        }
        if (tolerance == null || tolerance.isNegative() || tolerance.isZero()) {
            throw new IllegalArgumentException("容差必须为正");
        }
        if (tolerance.compareTo(Duration.ofHours(1)) > 0) {
            // 容差就是重放窗口。超过 1 小时的"容差"实际上是关掉了这道校验。
            throw new IllegalArgumentException("容差不得超过 1 小时：它等于重放窗口");
        }
        this.clock = clock;
        this.tolerance = tolerance;
    }

    public CallbackReplayGuard(Clock clock) {
        this(clock, DEFAULT_TOLERANCE);
    }

    /**
     * 校验微信支付的 {@code Wechatpay-Timestamp}（Unix 秒，字符串）。
     */
    public Verdict checkUnixSeconds(String timestamp) {
        if (timestamp == null || timestamp.isEmpty()) {
            return Verdict.MALFORMED;
        }
        long seconds;
        try {
            seconds = Long.parseLong(timestamp.trim());
        } catch (NumberFormatException notANumber) {
            return Verdict.MALFORMED;
        }
        // 负数或明显越界（超过 10 位数量级的年份）直接判畸形，
        // 避免 Instant.ofEpochSecond 抛异常或产生荒谬的时间点。
        if (seconds <= 0 || seconds > 253_402_300_799L) {   // 9999-12-31
            return Verdict.MALFORMED;
        }
        return check(Instant.ofEpochSecond(seconds));
    }

    /**
     * 校验任意已解析的时间点（支付宝回调里的 {@code notify_time} 解析后走这里）。
     */
    public Verdict check(Instant timestamp) {
        if (timestamp == null) {
            return Verdict.MALFORMED;
        }
        Instant now = clock.instant();
        if (timestamp.isBefore(now.minus(tolerance))) {
            return Verdict.TOO_OLD;
        }
        if (timestamp.isAfter(now.plus(tolerance))) {
            return Verdict.TOO_NEW;
        }
        return Verdict.ACCEPTED;
    }

    /** 便捷判定。调用方只关心通过与否时用这个。 */
    public boolean accepts(String unixSeconds) {
        return checkUnixSeconds(unixSeconds) == Verdict.ACCEPTED;
    }

    public Duration tolerance() {
        return tolerance;
    }
}
