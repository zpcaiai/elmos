import assert from "node:assert/strict";
import {
  boundedLedgerParam,
  describeTopupHandoffProblem,
  requireTopupAmountMinor,
  requireTopupIdempotencyKey,
  requireTopupOrderId,
  WalletTopupPolicyError,
} from "./walletTopupPolicy.ts";

let checks = 0;

function rejected(action, code) {
  assert.throws(action, (error) => {
    assert.ok(error instanceof WalletTopupPolicyError,
      `expected WalletTopupPolicyError, got ${error?.name}`);
    assert.equal(error.code, code);
    return true;
  });
  checks += 1;
}

function accepted(action, expected) {
  assert.deepEqual(action(), expected);
  checks += 1;
}

function problem(payload, fragment) {
  const found = describeTopupHandoffProblem(payload);
  assert.ok(found !== null, `expected a problem for ${JSON.stringify(payload)}`);
  assert.ok(found.includes(fragment),
    `expected problem to mention ${fragment}, got: ${found}`);
  checks += 1;
}

function clean(payload) {
  const found = describeTopupHandoffProblem(payload);
  assert.equal(found, null, `expected no problem, got: ${found}`);
  checks += 1;
}

// ---------------------------------------------------------------------------
// 幂等键。缺失、过短、含非法字符都必须挡下——这个键是「超时后重试」与
// 「开出第二笔可付款订单」之间唯一的区别。
// ---------------------------------------------------------------------------
rejected(() => requireTopupIdempotencyKey(null), "IDEMPOTENCY_KEY_INVALID");
rejected(() => requireTopupIdempotencyKey(""), "IDEMPOTENCY_KEY_INVALID");
rejected(() => requireTopupIdempotencyKey("short"), "IDEMPOTENCY_KEY_INVALID");
rejected(() => requireTopupIdempotencyKey("-leading-dash-is-invalid"),
  "IDEMPOTENCY_KEY_INVALID");
rejected(() => requireTopupIdempotencyKey("has space in it"), "IDEMPOTENCY_KEY_INVALID");
rejected(() => requireTopupIdempotencyKey(`topup-${"x".repeat(200)}`),
  "IDEMPOTENCY_KEY_INVALID");
accepted(() => requireTopupIdempotencyKey("topup-01234567-89ab-cdef-0123-456789abcdef"),
  "topup-01234567-89ab-cdef-0123-456789abcdef");

// ---------------------------------------------------------------------------
// 订单号。斜杠是重点：这个值会被拼进上游 URL。
// ---------------------------------------------------------------------------
rejected(() => requireTopupOrderId("../../commercial/v1/billing/subscriptions/current"),
  "TOPUP_ORDER_ID_INVALID");
rejected(() => requireTopupOrderId("topup-abc/../../etc"), "TOPUP_ORDER_ID_INVALID");
rejected(() => requireTopupOrderId(""), "TOPUP_ORDER_ID_INVALID");
rejected(() => requireTopupOrderId("-starts-with-dash"), "TOPUP_ORDER_ID_INVALID");
accepted(() => requireTopupOrderId("topup-01234567-89ab-cdef-0123-456789abcdef"),
  "topup-01234567-89ab-cdef-0123-456789abcdef");

// ---------------------------------------------------------------------------
// 金额。零、负数、小数、字符串、超出安全整数范围都不是「大于零的整数分」。
// 上限刻意不在这里判——那是数据库的事，见函数注释。
// ---------------------------------------------------------------------------
rejected(() => requireTopupAmountMinor(null), "TOPUP_AMOUNT_INVALID");
rejected(() => requireTopupAmountMinor({}), "TOPUP_AMOUNT_INVALID");
rejected(() => requireTopupAmountMinor({ amountMinor: 0 }), "TOPUP_AMOUNT_INVALID");
rejected(() => requireTopupAmountMinor({ amountMinor: -100 }), "TOPUP_AMOUNT_INVALID");
rejected(() => requireTopupAmountMinor({ amountMinor: 10.5 }), "TOPUP_AMOUNT_INVALID");
rejected(() => requireTopupAmountMinor({ amountMinor: "10000" }), "TOPUP_AMOUNT_INVALID");
rejected(() => requireTopupAmountMinor({ amountMinor: Number.NaN }), "TOPUP_AMOUNT_INVALID");
rejected(() => requireTopupAmountMinor({ amountMinor: Number.POSITIVE_INFINITY }),
  "TOPUP_AMOUNT_INVALID");
rejected(() => requireTopupAmountMinor({ amountMinor: 2 ** 53 }), "TOPUP_AMOUNT_INVALID");
// 数组不是对象字面量：[].amountMinor 是 undefined，但显式挡下更清楚
rejected(() => requireTopupAmountMinor([{ amountMinor: 100 }]), "TOPUP_AMOUNT_INVALID");
accepted(() => requireTopupAmountMinor({ amountMinor: 1 }), 1);
accepted(() => requireTopupAmountMinor({ amountMinor: 5_000_000 }), 5_000_000);

// ---------------------------------------------------------------------------
// 交接响应形态。这一组是「用户点了付款却什么都没发生」的唯一防线。
// ---------------------------------------------------------------------------
problem(null, "不是对象");
problem("ALIPAY_CHECKOUT", "不是对象");
problem([], "不是对象");
problem({}, "paymentProvider");
problem({ paymentProvider: "STRIPE_CHECKOUT", checkoutUrl: "https://stripe.example/pay" },
  "paymentProvider");   // 充值不收 Stripe，即使形态完整也要挡
problem({ paymentProvider: "ALIPAY_CHECKOUT" }, "既没有跳转地址也没有二维码");
problem({ paymentProvider: "ALIPAY_CHECKOUT", checkoutUrl: "" },
  "既没有跳转地址也没有二维码");
problem({
  paymentProvider: "ALIPAY_CHECKOUT",
  checkoutUrl: "https://alipay.example/pay",
  qrCodeUrl: "weixin://wxpay/bizpayurl?pr=abc",
}, "同时给了跳转地址与二维码");
problem({ paymentProvider: "WECHAT_PAY_NATIVE", checkoutUrl: "https://wx.example/pay" },
  "必须返回二维码内容");
problem({ paymentProvider: "ALIPAY_CHECKOUT", qrCodeUrl: "weixin://wxpay/bizpayurl?pr=abc" },
  "必须返回跳转地址");
// 非字符串的 URL 与缺失等价：一个 { checkoutUrl: 42 } 同样点不动
problem({ paymentProvider: "ALIPAY_CHECKOUT", checkoutUrl: 42 },
  "既没有跳转地址也没有二维码");

clean({ paymentProvider: "ALIPAY_CHECKOUT", checkoutUrl: "https://alipay.example/pay" });
clean({ paymentProvider: "WECHAT_PAY_NATIVE", qrCodeUrl: "weixin://wxpay/bizpayurl?pr=abc" });
clean({
  paymentProvider: "WECHAT_PAY_NATIVE",
  qrCodeUrl: "weixin://wxpay/bizpayurl?pr=abc",
  checkoutUrl: null,
});

// ---------------------------------------------------------------------------
// 流水分页夹逼。空、负、小数、超大都回落或截断，不抛错——分页参数不值得
// 让整个页面失败。
// ---------------------------------------------------------------------------
accepted(() => boundedLedgerParam(null, 50, 200), 50);
accepted(() => boundedLedgerParam("", 50, 200), 50);
accepted(() => boundedLedgerParam("abc", 50, 200), 50);
accepted(() => boundedLedgerParam("-1", 50, 200), 50);
accepted(() => boundedLedgerParam("10.5", 50, 200), 50);
accepted(() => boundedLedgerParam("1000000", 50, 200), 200);
accepted(() => boundedLedgerParam("0", 50, 200), 0);
accepted(() => boundedLedgerParam("25", 50, 200), 25);

console.log(`walletTopupPolicy: ${checks} checks passed`);
