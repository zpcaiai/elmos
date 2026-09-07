package io.elmos.commercialapi;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.commercialadapter.payment.WechatPayCallbackAdapter;

/**
 * {@link WechatPayCallbackAdapter.NotificationReader} 的 Jackson 实现。
 *
 * <p>它单独存在，是为了让 {@code io.elmos.commercialadapter.payment} 包保持
 * 只依赖 JDK（那样整包能脱离 Maven 单独编译自检）。Jackson 的耦合止步于本类。
 *
 * <p><b>所有字段缺失都抛异常，没有默认值。</b>把缺失的金额当成 0、
 * 把缺失的 {@code trade_state} 当成空串，都会让下游的判断在错误的前提上进行。
 * 这条路径决定的是收钱结果，宁可失败也不要猜。
 */
public final class JacksonWechatNotificationReader
        implements WechatPayCallbackAdapter.NotificationReader {

    private final ObjectMapper json;

    public JacksonWechatNotificationReader(ObjectMapper json) {
        if (json == null) {
            throw new IllegalArgumentException("ObjectMapper 未注入");
        }
        this.json = json;
    }

    @Override
    public WechatPayCallbackAdapter.Envelope readEnvelope(String rawBody) {
        JsonNode root = parse(rawBody, "微信回调外层报文");
        JsonNode resource = root.path("resource");
        if (!resource.isObject()) {
            throw new IllegalStateException("微信回调缺少 resource 对象");
        }
        // associated_data 允许缺省（文档里它可以不存在），其余三个必需。
        return new WechatPayCallbackAdapter.Envelope(
                text(root, "id"),
                text(root, "event_type"),
                text(resource, "ciphertext"),
                text(resource, "nonce"),
                resource.path("associated_data").asText(""));
    }

    @Override
    public WechatPayCallbackAdapter.Resource readResource(String plaintext) {
        JsonNode root = parse(plaintext, "微信回调资源明文");
        JsonNode amount = root.path("amount");
        if (!amount.isObject()) {
            throw new IllegalStateException("微信回调资源缺少 amount 对象");
        }
        JsonNode total = amount.path("total");
        // canConvertToLong 会挡掉小数与超长整数。金额字段是 int（分），
        // 出现小数说明对面传的不是我们以为的单位，必须失败而不是四舍五入。
        if (!total.canConvertToLong() || total.longValue() < 0) {
            throw new IllegalStateException("微信回调 amount.total 非法");
        }
        return new WechatPayCallbackAdapter.Resource(
                text(root, "out_trade_no"),
                text(root, "transaction_id"),
                text(root, "trade_state"),
                total.longValue(),
                text(root, "mchid"),
                text(amount, "currency"));
    }

    private JsonNode parse(String value, String what) {
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(what + "为空");
        }
        try {
            JsonNode root = json.readTree(value);
            if (!root.isObject()) {
                throw new IllegalStateException(what + "不是 JSON 对象");
            }
            return root;
        } catch (com.fasterxml.jackson.core.JsonProcessingException malformed) {
            throw new IllegalStateException(what + "不是合法 JSON", malformed);
        }
    }

    private static String text(JsonNode node, String field) {
        JsonNode value = node.path(field);
        if (!value.isTextual() || value.asText().isBlank()) {
            throw new IllegalStateException("微信回调缺少必需字段: " + field);
        }
        return value.asText();
    }
}
