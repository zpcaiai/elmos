package io.elmos.commercialadapter.payment;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.Base64;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

/** Verifies and normalizes ELMPay's versioned, signed business-event envelope. */
public final class ElmPayWebhookAdapter implements PaymentCallbackPipeline.ProviderAdapter {
    private static final Set<String> ENVELOPE_FIELDS = Set.of(
            "event_id", "event_name", "event_version", "tenant_id", "project_id",
            "aggregate_type", "aggregate_id", "revision", "occurred_at", "recorded_at",
            "trace_id", "payload");
    private static final Set<String> CAPTURED_FIELDS = Set.of(
            "payment_intent_id", "project_id", "provider", "captured_at", "amount_minor",
            "currency", "business_order_digest");

    @FunctionalInterface
    public interface SecretProvider {
        byte[] secret();
    }

    private final PaymentProvider provider;
    private final UUID tenantId;
    private final UUID projectId;
    private final String keyId;
    private final SecretProvider secrets;
    private final CallbackReplayGuard replayGuard;
    private final ObjectMapper mapper;

    public ElmPayWebhookAdapter(PaymentProvider provider, UUID tenantId, UUID projectId,
            String keyId, Path secretFile, CallbackReplayGuard replayGuard, ObjectMapper mapper) {
        this(provider, tenantId, projectId, keyId, () -> readSecret(secretFile),
                replayGuard, mapper);
    }

    public ElmPayWebhookAdapter(PaymentProvider provider, UUID tenantId, UUID projectId,
            String keyId, SecretProvider secrets, CallbackReplayGuard replayGuard,
            ObjectMapper mapper) {
        this.provider = Objects.requireNonNull(provider, "provider");
        if (provider != PaymentProvider.ALIPAY_CHECKOUT
                && provider != PaymentProvider.WECHAT_PAY_NATIVE) {
            throw new IllegalArgumentException("ELMPay 回调仅允许支付宝或微信支付通道");
        }
        this.tenantId = Objects.requireNonNull(tenantId, "tenantId");
        this.projectId = Objects.requireNonNull(projectId, "projectId");
        if (keyId == null || !keyId.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")) {
            throw new IllegalArgumentException("ELMPay webhook key ID 非法");
        }
        this.keyId = keyId;
        this.secrets = Objects.requireNonNull(secrets, "secrets");
        this.replayGuard = Objects.requireNonNull(replayGuard, "replayGuard");
        this.mapper = Objects.requireNonNull(mapper, "mapper");
    }

    @Override
    public boolean acceptsTimestamp(PaymentCallbackPipeline.RawCallback raw) {
        return replayGuard.accepts(header(raw.headers(), "X-Elmpay-Timestamp"));
    }

    public PaymentProvider provider() {
        return provider;
    }

    @Override
    public boolean verifySignature(PaymentCallbackPipeline.RawCallback raw) {
        try {
            String timestamp = header(raw.headers(), "X-Elmpay-Timestamp");
            String suppliedKeyId = header(raw.headers(), "X-Elmpay-Key-Id");
            String suppliedEventId = header(raw.headers(), "X-Elmpay-Event-Id");
            String suppliedEventType = header(raw.headers(), "X-Elmpay-Event-Type");
            if (!keyId.equals(suppliedKeyId) || timestamp == null
                    || suppliedEventId == null || suppliedEventType == null) {
                return false;
            }
            String signature = header(raw.headers(), "X-Elmpay-Signature");
            if (signature == null) return false;
            String prefix = "t=" + timestamp + ",v1=";
            if (!signature.startsWith(prefix) || signature.length() <= prefix.length()) {
                return false;
            }
            byte[] expected;
            byte[] secret = secrets.secret();
            try {
                if (secret.length < 32 || secret.length > 128) return false;
                Mac mac = Mac.getInstance("HmacSHA256");
                mac.init(new SecretKeySpec(secret, "HmacSHA256"));
                expected = mac.doFinal((timestamp + "." + raw.rawBody())
                        .getBytes(StandardCharsets.UTF_8));
            } finally {
                java.util.Arrays.fill(secret, (byte) 0);
            }
            byte[] supplied = Base64.getUrlDecoder().decode(signature.substring(prefix.length()));
            try {
                if (!MessageDigest.isEqual(expected, supplied)) return false;
            } finally {
                java.util.Arrays.fill(expected, (byte) 0);
                java.util.Arrays.fill(supplied, (byte) 0);
            }
            JsonNode envelope = parseEnvelope(raw.rawBody());
            return suppliedEventId.equals(envelope.path("event_id").asText())
                    && suppliedEventType.equals(envelope.path("event_name").asText());
        } catch (RuntimeException | java.security.GeneralSecurityException failure) {
            return false;
        }
    }

    public boolean isCapturedEvent(PaymentCallbackPipeline.RawCallback raw) {
        return "payment_intent.captured".equals(
                parseEnvelope(raw.rawBody()).path("event_name").asText());
    }

    @Override
    public PaymentCallbackPipeline.NormalizedCallback normalize(
            PaymentCallbackPipeline.RawCallback raw) {
        JsonNode root = parseEnvelope(raw.rawBody());
        if (!"payment_intent.captured".equals(root.path("event_name").asText())
                || root.path("event_version").asInt() != 1
                || !"payment_intent".equals(root.path("aggregate_type").asText())) {
            throw new IllegalArgumentException("不支持的 ELMPay 事件类型或版本");
        }
        JsonNode payload = root.path("payload");
        if (!payload.isObject() || !fieldNames(payload).equals(CAPTURED_FIELDS)) {
            throw new IllegalArgumentException("ELMPay captured payload 契约不匹配");
        }
        String expectedProvider = provider == PaymentProvider.ALIPAY_CHECKOUT
                ? "alipay" : "wechat";
        if (!expectedProvider.equals(payload.path("provider").asText())
                || !projectId.toString().equals(payload.path("project_id").asText())
                || !"CNY".equals(payload.path("currency").asText())) {
            throw new SecurityException("ELMPay captured 事件绑定不匹配");
        }
        JsonNode amountNode = payload.path("amount_minor");
        if (!amountNode.isIntegralNumber() || !amountNode.canConvertToLong()) {
            throw new IllegalArgumentException("ELMPay captured 金额必须是 int64 最小货币单位");
        }
        long amount = amountNode.longValue();
        String digest = payload.path("business_order_digest").asText("");
        UUID paymentIntentId = UUID.fromString(payload.path("payment_intent_id").asText());
        Instant.parse(payload.path("captured_at").asText());
        if (!paymentIntentId.toString().equals(root.path("aggregate_id").asText())
                || amount <= 0 || !digest.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("ELMPay captured 金额或订单摘要非法");
        }
        return new PaymentCallbackPipeline.NormalizedCallback(provider,
                root.path("event_id").asText(), "sha256:" + digest, amount, "CAPTURED");
    }

    @Override
    public boolean indicatesPaymentSuccess(PaymentCallbackPipeline.NormalizedCallback callback) {
        return "CAPTURED".equals(callback.tradeStatus());
    }

    private JsonNode parseEnvelope(String rawBody) {
        try {
            JsonNode root = mapper.readTree(rawBody);
            if (!root.isObject() || !fieldNames(root).equals(ENVELOPE_FIELDS)
                    || !tenantId.toString().equals(root.path("tenant_id").asText())
                    || !projectId.toString().equals(root.path("project_id").asText())) {
                throw new SecurityException("ELMPay 事件 envelope 绑定或字段不匹配");
            }
            JsonNode eventVersion = root.path("event_version");
            JsonNode revision = root.path("revision");
            if (!eventVersion.isIntegralNumber() || !eventVersion.canConvertToInt()
                    || eventVersion.intValue() <= 0 || !revision.isIntegralNumber()
                    || !revision.canConvertToLong() || revision.longValue() <= 0) {
                throw new IllegalArgumentException("ELMPay 事件版本或 revision 非法");
            }
            UUID.fromString(root.path("event_id").asText());
            UUID.fromString(root.path("aggregate_id").asText());
            Instant.parse(root.path("occurred_at").asText());
            Instant.parse(root.path("recorded_at").asText());
            return root;
        } catch (java.io.IOException failure) {
            throw new IllegalArgumentException("ELMPay 事件 JSON 非法", failure);
        }
    }

    private static Set<String> fieldNames(JsonNode node) {
        Set<String> names = new LinkedHashSet<>();
        node.fieldNames().forEachRemaining(names::add);
        return names;
    }

    private static String header(Map<String, String> headers, String wanted) {
        if (headers == null) return null;
        return headers.entrySet().stream()
                .filter(entry -> wanted.equalsIgnoreCase(entry.getKey()))
                .map(Map.Entry::getValue).findFirst().orElse(null);
    }

    private static byte[] readSecret(Path secretFile) {
        Path path = Objects.requireNonNull(secretFile, "secretFile");
        if (!path.isAbsolute() || Files.isSymbolicLink(path)
                || !Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) {
            throw new SecurityException("ELMPay webhook secret 文件必须是绝对路径普通文件且不能是符号链接");
        }
        try {
            long size = Files.size(path);
            if (size < 32 || size > 128) {
                throw new SecurityException("ELMPay webhook secret 文件大小必须为 32..128 字节");
            }
            return Files.readAllBytes(path);
        } catch (java.io.IOException failure) {
            throw new IllegalStateException("无法读取 ELMPay webhook secret 文件", failure);
        }
    }
}
