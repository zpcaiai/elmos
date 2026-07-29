package io.elmos.commercialadapter.payment;

/**
 * 定价目录以「分」为唯一权威金额单位（{@code priceFen}）。两家提供方的金额格式不同：
 *
 * <ul>
 *   <li>支付宝：<b>元</b>，字符串，恰好两位小数（{@code total_amount}）</li>
 *   <li>微信支付：<b>分</b>，整数（{@code amount.total}）</li>
 * </ul>
 *
 * <p>这里全部使用整数运算。金额换算一旦引入 {@code double}/{@code float}，
 * 就会出现 {@code 12900 / 100.0 * 100 != 12900} 这类误差，
 * 而支付场景里一分钱的偏差会直接导致签名比对失败或对账长期挂账。
 *
 * <p>本类无外部依赖，可独立编译与测试。
 */
public final class MoneyConversion {

    /** 单笔金额上限保护：1 亿元。超过一律拒绝，避免单位写错导致天价订单。 */
    static final long MAX_FEN = 10_000_000_000L;

    private MoneyConversion() {
    }

    /**
     * 分 → 支付宝金额字符串（元，恰好两位小数）。
     *
     * @throws IllegalArgumentException 金额为负、为零或超过上限
     */
    public static String toAlipayYuan(long fen) {
        assertPayable(fen);
        long yuan = fen / 100;
        long remainder = fen % 100;
        return yuan + "." + (remainder < 10 ? "0" + remainder : Long.toString(remainder));
    }

    /**
     * 分 → 微信支付金额（分，整数）。
     *
     * @throws IllegalArgumentException 金额非法，或超出 {@code int} 表示范围
     */
    public static int toWechatFen(long fen) {
        assertPayable(fen);
        if (fen > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("金额超出微信支付 int 字段范围: " + fen);
        }
        return (int) fen;
    }

    /**
     * 支付宝金额字符串 → 分。用于回调金额比对。
     *
     * <p>只接受 {@code 整数部分.两位小数} 与纯整数两种形式；
     * 三位小数、科学计数法、前后空白、正负号一律拒绝，
     * 因为回调金额比对必须是精确匹配，不能"尽量解析"。
     *
     * @throws IllegalArgumentException 格式非法
     */
    public static long fromAlipayYuan(String amount) {
        if (amount == null || amount.isEmpty()) {
            throw new IllegalArgumentException("金额为空");
        }
        if (!amount.matches("\\d{1,12}(\\.\\d{2})?")) {
            throw new IllegalArgumentException("支付宝金额格式非法: " + amount);
        }
        int dot = amount.indexOf('.');
        long yuan = Long.parseLong(dot < 0 ? amount : amount.substring(0, dot));
        long cents = dot < 0 ? 0 : Long.parseLong(amount.substring(dot + 1));
        long fen = yuan * 100 + cents;
        assertPayable(fen);
        return fen;
    }

    /**
     * 回调金额是否与本地订单一致。不一致必须拒绝回调，且不得更新订阅状态。
     */
    public static boolean matchesExpected(long expectedFen, long callbackFen) {
        return expectedFen == callbackFen;
    }

    private static void assertPayable(long fen) {
        if (fen <= 0) {
            throw new IllegalArgumentException("可支付金额必须为正: " + fen);
        }
        if (fen > MAX_FEN) {
            throw new IllegalArgumentException("金额超过上限保护 " + MAX_FEN + " 分: " + fen);
        }
    }
}
