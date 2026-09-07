package io.elmos.network;

import java.net.InetAddress;
import java.net.URI;
import java.time.Clock;
import java.util.Locale;
import java.util.Objects;

public final class NetworkDecisionService {
    public record Decision(boolean allowed, String reason, String policyId, int policyVersion) {}
    private final Clock clock;
    public NetworkDecisionService(Clock clock) { this.clock = Objects.requireNonNull(clock); }

    public Decision decide(NetworkPolicy policy, URI destination, InetAddress[] resolvedAddresses) {
        Objects.requireNonNull(policy); Objects.requireNonNull(destination);
        if (policy.expiresAt() != null && !policy.expiresAt().isAfter(clock.instant())) return deny(policy, "policy expired");
        if (!"https".equalsIgnoreCase(destination.getScheme())) return deny(policy, "only HTTPS is allowed");
        if (destination.getUserInfo() != null) return deny(policy, "userinfo is forbidden");
        String host = destination.getHost();
        if (host == null || isIpLiteral(host)) return deny(policy, "IP literals and invalid hosts are forbidden");
        host = host.toLowerCase(Locale.ROOT);
        if (!policy.allowedHosts().contains(host)) return deny(policy, "host is not allowlisted");
        if (resolvedAddresses == null || resolvedAddresses.length == 0) return deny(policy, "DNS resolution evidence is missing");
        for (InetAddress address : resolvedAddresses) if (forbidden(address)) return deny(policy, "DNS resolved to a forbidden address range");
        return new Decision(true, "allowed by exact host rule", policy.policyId(), policy.version());
    }

    private static boolean forbidden(InetAddress address) {
        return address == null || address.isAnyLocalAddress() || address.isLoopbackAddress() || address.isLinkLocalAddress()
                || address.isSiteLocalAddress() || address.isMulticastAddress();
    }
    private static boolean isIpLiteral(String host) { return host.matches("[0-9.]+") || host.contains(":"); }
    private static Decision deny(NetworkPolicy policy, String reason) { return new Decision(false, reason, policy.policyId(), policy.version()); }
}
