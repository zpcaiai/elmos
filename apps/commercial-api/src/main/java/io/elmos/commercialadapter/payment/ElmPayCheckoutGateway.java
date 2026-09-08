package io.elmos.commercialadapter.payment;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.HexFormat;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

/** ELMOS checkout adapter for ELMPay's tenant/project-bound hosted checkout API. */
public final class ElmPayCheckoutGateway implements PaymentProviderRouter.CheckoutGateway {
    private static final Set<String> RESPONSE_FIELDS = Set.of(
            "checkout_session_id", "payment_intent_id", "expires_at", "checkout_url", "status");

    @FunctionalInterface
    public interface TokenProvider {
        String token();
    }

    @FunctionalInterface
    public interface Transport {
        Response post(URI endpoint, String token, UUID projectId, String idempotencyKey,
                String requestId, String traceparent, String jsonBody);
    }

    public record Response(int statusCode, String body) {
        public Response {
            if (statusCode < 100 || statusCode > 599 || body == null) {
                throw new IllegalArgumentException("ELMPay 响应非法");
            }
        }
    }

    private final PaymentProvider provider;
    private final URI endpoint;
    private final UUID projectId;
    private final String returnRouteId;
    private final boolean allowHttpForLocalSandbox;
    private final TokenProvider tokens;
    private final Transport transport;
    private final ObjectMapper mapper;

    public ElmPayCheckoutGateway(PaymentProvider provider, URI baseUri, UUID projectId,
            String returnRouteId, boolean allowHttpForLocalSandbox, Path tokenFile,
            HttpClient client, ObjectMapper mapper) {
        this(provider, baseUri, projectId, returnRouteId, allowHttpForLocalSandbox,
                () -> readToken(tokenFile), jdkTransport(client), mapper);
    }

    public ElmPayCheckoutGateway(PaymentProvider provider, URI baseUri, UUID projectId,
            String returnRouteId, boolean allowHttpForLocalSandbox, TokenProvider tokens,
            Transport transport, ObjectMapper mapper) {
        this.provider = Objects.requireNonNull(provider, "provider");
        if (provider != PaymentProvider.ALIPAY_CHECKOUT
                && provider != PaymentProvider.WECHAT_PAY_NATIVE) {
            throw new IllegalArgumentException("ELMPay 仅允许支付宝或微信支付通道");
        }
        URI normalized = Objects.requireNonNull(baseUri, "baseUri").normalize();
        if (normalized.getHost() == null || normalized.getUserInfo() != null
                || normalized.getQuery() != null || normalized.getFragment() != null
                || !("https".equalsIgnoreCase(normalized.getScheme())
                || (allowHttpForLocalSandbox
                && "http".equalsIgnoreCase(normalized.getScheme())
                && isLoopback(normalized.getHost())))) {
            throw new IllegalArgumentException("ELMPay base URI 必须是 HTTPS；本地沙箱只允许 loopback HTTP");
        }
        String root = normalized.toString();
        if (!root.endsWith("/")) root += "/";
        this.endpoint = URI.create(root).resolve("v1/checkout-sessions");
        this.projectId = Objects.requireNonNull(projectId, "projectId");
        if (returnRouteId == null || !returnRouteId.matches("[a-z0-9][a-z0-9._-]{0,63}")) {
            throw new IllegalArgumentException("ELMPay return route ID 非法");
        }
        this.returnRouteId = returnRouteId;
        this.allowHttpForLocalSandbox = allowHttpForLocalSandbox;
        this.tokens = Objects.requireNonNull(tokens, "tokens");
        this.transport = Objects.requireNonNull(transport, "transport");
        this.mapper = Objects.requireNonNull(mapper, "mapper");
    }

    @Override
    public PaymentProvider provider() {
        return provider;
    }

    @Override
    public PaymentProviderRouter.CheckoutHandoff prepare(
            String outTradeNo, long amountFen, String subject) {
        if (outTradeNo == null || outTradeNo.isBlank() || outTradeNo.length() > 128
                || amountFen <= 0 || subject == null || subject.isBlank()) {
            throw new IllegalArgumentException("ELMPay 下单参数非法");
        }
        String digest = sha256(outTradeNo);
        String requestId = "elmos-" + digest.substring(0, 32);
        String traceparent = "00-" + digest.substring(0, 32) + "-"
                + digest.substring(32, 48) + "-01";
        String body;
        try {
            body = mapper.writeValueAsString(java.util.Map.of(
                    "business_order_no", outTradeNo,
                    "amount", amountFen,
                    "currency", "CNY",
                    "payment_method", provider == PaymentProvider.ALIPAY_CHECKOUT
                            ? "alipay" : "wechat",
                    "return_route_id", returnRouteId));
        } catch (Exception failure) {
            throw new IllegalStateException("ELMPay 下单请求序列化失败", failure);
        }
        Response response = transport.post(endpoint, tokens.token(), projectId,
                "elmos-checkout-" + digest, requestId, traceparent, body);
        if (response.statusCode() != 201) {
            throw new IllegalStateException("ELMPay 下单返回 HTTP " + response.statusCode());
        }
        try {
            JsonNode root = mapper.readTree(response.body());
            java.util.LinkedHashSet<String> names = new java.util.LinkedHashSet<>();
            root.fieldNames().forEachRemaining(names::add);
            if (!root.isObject() || !names.equals(RESPONSE_FIELDS)
                    || !"OPEN".equals(root.path("status").asText())) {
                throw new IllegalArgumentException("ELMPay 下单响应结构或状态非法");
            }
            requireText(root, "checkout_session_id", 160);
            UUID.fromString(requireText(root, "payment_intent_id", 36));
            java.time.Instant.parse(requireText(root, "expires_at", 64));
            URI checkoutUrl = URI.create(requireText(root, "checkout_url", 4096));
            if (checkoutUrl.getHost() == null || checkoutUrl.getUserInfo() != null
                    || !("https".equalsIgnoreCase(checkoutUrl.getScheme())
                    || (allowHttpForLocalSandbox
                    && "http".equalsIgnoreCase(checkoutUrl.getScheme())
                    && isLoopback(checkoutUrl.getHost())))) {
                throw new IllegalArgumentException("ELMPay checkout URL 非法");
            }
            return new PaymentProviderRouter.CheckoutHandoff(
                    provider, checkoutUrl.toString(), null);
        } catch (RuntimeException failure) {
            throw new IllegalStateException("ELMPay 下单响应校验失败", failure);
        } catch (Exception failure) {
            throw new IllegalStateException("ELMPay 下单响应解析失败", failure);
        }
    }

    @Override
    public boolean contactsProviderDuringPrepare() {
        return true;
    }

    private static Transport jdkTransport(HttpClient client) {
        HttpClient http = Objects.requireNonNull(client, "client");
        return (endpoint, token, projectId, idempotencyKey, requestId, traceparent, jsonBody) -> {
            if (token == null || token.isBlank() || token.length() > 4096
                    || token.indexOf('\r') >= 0 || token.indexOf('\n') >= 0) {
                throw new SecurityException("ELMPay API token 非法");
            }
            try {
                HttpRequest request = HttpRequest.newBuilder(endpoint)
                        .timeout(Duration.ofSeconds(10))
                        .header("Authorization", "Bearer " + token)
                        .header("X-Project-Id", projectId.toString())
                        .header("Idempotency-Key", idempotencyKey)
                        .header("X-Request-Id", requestId)
                        .header("traceparent", traceparent)
                        .header("Accept", "application/json")
                        .header("Content-Type", "application/json")
                        .POST(HttpRequest.BodyPublishers.ofString(jsonBody, StandardCharsets.UTF_8))
                        .build();
                HttpResponse<String> response = http.send(
                        request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
                return new Response(response.statusCode(), response.body());
            } catch (InterruptedException failure) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("ELMPay 下单被中断", failure);
            } catch (Exception failure) {
                throw new IllegalStateException("ELMPay 下单请求失败，结果未知", failure);
            }
        };
    }

    private static String readToken(Path tokenFile) {
        Path path = Objects.requireNonNull(tokenFile, "tokenFile");
        if (!path.isAbsolute() || Files.isSymbolicLink(path)
                || !Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) {
            throw new SecurityException("ELMPay API token 文件必须是绝对路径普通文件且不能是符号链接");
        }
        try {
            if (Files.size(path) > 4096) {
                throw new SecurityException("ELMPay API token 文件过大");
            }
            return Files.readString(path, StandardCharsets.UTF_8).strip();
        } catch (java.io.IOException failure) {
            throw new IllegalStateException("无法读取 ELMPay API token 文件", failure);
        }
    }

    private static String requireText(JsonNode root, String field, int maximum) {
        String value = root.path(field).asText("");
        if (value.isBlank() || value.length() > maximum) {
            throw new IllegalArgumentException("ELMPay 响应字段非法: " + field);
        }
        return value;
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (java.security.NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("SHA-256 不可用", impossible);
        }
    }

    private static boolean isLoopback(String host) {
        return "localhost".equalsIgnoreCase(host) || "127.0.0.1".equals(host)
                || "[::1]".equals(host) || "::1".equals(host);
    }
}
