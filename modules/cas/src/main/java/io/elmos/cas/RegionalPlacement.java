package io.elmos.cas;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;

/**
 * ELMOS-CAS-018 regional policy. Decides <em>where</em> an object is allowed to be, before it is
 * written anywhere.
 *
 * <p>Residency is not a label you attach after the fact. Once bytes derived from a customer's
 * source have been written to a bucket in the wrong jurisdiction, no amount of metadata fixes it
 * — the only remedy is deletion plus a disclosure. So the placement decision happens on the way
 * in, it is total (an unmapped residency is refused, never defaulted), and replication targets
 * are enumerated rather than inferred.
 *
 * <p>Deliberately separate from {@link CasAccessPolicy}: that one answers "may this reader see
 * it", this one answers "may these bytes exist here". A reader in the right region with the wrong
 * permissions must still be refused, and vice versa.
 */
public final class RegionalPlacement {

    private RegionalPlacement() {
    }

    /**
     * @param primaryRegion    where the authoritative copy lives
     * @param replicaRegions   additional regions the object may be copied to, in preference order
     * @param requiresReplication true when a write is not considered complete until at least one
     *                            replica has it — the durability requirement for regulated data
     */
    public record PlacementRule(String dataResidency,
                                String primaryRegion,
                                List<String> replicaRegions,
                                boolean requiresReplication) {
        public PlacementRule {
            dataResidency = CasText.required(dataResidency, "dataResidency");
            primaryRegion = CasText.required(primaryRegion, "primaryRegion");
            replicaRegions = List.copyOf(replicaRegions);
            if (replicaRegions.contains(primaryRegion)) {
                throw new IllegalArgumentException("primary region " + primaryRegion + " listed as its own replica");
            }
            if (requiresReplication && replicaRegions.isEmpty()) {
                throw new IllegalArgumentException("replication required for " + dataResidency
                        + " but no replica region is declared");
            }
        }

        public Set<String> allRegions() {
            Set<String> regions = new LinkedHashSet<>();
            regions.add(primaryRegion);
            regions.addAll(replicaRegions);
            return Collections.unmodifiableSet(regions);
        }
    }

    public record Placement(String dataResidency, String primaryRegion, List<String> replicaRegions,
                            boolean requiresReplication) {
    }

    public record Decision(boolean allowed, String reason, String detail) {
        static Decision allow() {
            return new Decision(true, "ALLOWED", "");
        }

        static Decision deny(String reason, String detail) {
            return new Decision(false, reason, detail);
        }
    }

    public static final class Policy {

        private final Map<String, PlacementRule> rules = new TreeMap<>();

        public Policy withRule(PlacementRule rule) {
            if (rules.putIfAbsent(rule.dataResidency(), rule) != null) {
                throw new IllegalArgumentException("duplicate placement rule for " + rule.dataResidency());
            }
            return this;
        }

        /** @throws CasExceptions.CasAccessDeniedException when the residency has no rule at all */
        public Placement place(String dataResidency) {
            PlacementRule rule = rules.get(CasText.required(dataResidency, "dataResidency"));
            if (rule == null) {
                // Defaulting here is the failure mode this class exists to prevent: an unmapped
                // residency would silently land in whatever region happened to be configured.
                throw new CasExceptions.CasAccessDeniedException("RESIDENCY_NOT_MAPPED", dataResidency);
            }
            return new Placement(rule.dataResidency(), rule.primaryRegion(), rule.replicaRegions(),
                    rule.requiresReplication());
        }

        /** May an object of this residency be stored in this region at all? */
        public Decision admitWrite(String region, String dataResidency) {
            PlacementRule rule = rules.get(dataResidency);
            if (rule == null) {
                return Decision.deny("RESIDENCY_NOT_MAPPED", dataResidency);
            }
            if (!rule.allRegions().contains(region)) {
                return Decision.deny("REGION_NOT_PERMITTED_FOR_RESIDENCY",
                        dataResidency + " may only occupy " + rule.allRegions() + ", not " + region);
            }
            return Decision.allow();
        }

        public Decision admitRead(String readerRegion, String dataResidency) {
            return admitWrite(readerRegion, dataResidency);
        }

        public Set<String> mappedResidencies() {
            return Collections.unmodifiableSet(new LinkedHashSet<>(rules.keySet()));
        }
    }

    /**
     * Routes objects to region-bound stores according to a {@link Policy}.
     *
     * <p>Replication is recorded as a backlog rather than performed inline for the same reason the
     * tiered store queues write-back: the caller that knows whether this particular object owes
     * durability is the caller, not the router. {@link #replicate()} drains it, and
     * {@link #outstandingReplication()} is what an alert rule watches.
     */
    public static final class Router {

        private final Policy policy;
        private final Map<String, CasStore> storesByRegion;
        private final Map<CasDigest, List<String>> replicationBacklog = new LinkedHashMap<>();

        public Router(Policy policy, Map<String, CasStore> storesByRegion) {
            this.policy = Objects.requireNonNull(policy, "policy");
            this.storesByRegion = Map.copyOf(storesByRegion);
            for (String residency : policy.mappedResidencies()) {
                for (String region : policy.place(residency).replicaRegions()) {
                    requireStore(region);
                }
                requireStore(policy.place(residency).primaryRegion());
            }
        }

        /**
         * @return the region the authoritative copy was written to
         * @throws CasExceptions.CasAccessDeniedException when residency and region disagree
         */
        public String put(String dataResidency, CasDigest digest, byte[] content) {
            Placement placement = policy.place(dataResidency);
            Decision decision = policy.admitWrite(placement.primaryRegion(), dataResidency);
            if (!decision.allowed()) {
                throw new CasExceptions.CasAccessDeniedException(decision.reason(), decision.detail());
            }
            requireStore(placement.primaryRegion()).put(digest, content);
            if (!placement.replicaRegions().isEmpty()) {
                replicationBacklog.put(digest, new ArrayList<>(placement.replicaRegions()));
            }
            if (placement.requiresReplication()) {
                replicate();
            }
            return placement.primaryRegion();
        }

        public byte[] get(String readerRegion, String dataResidency, CasDigest digest) {
            Decision decision = policy.admitRead(readerRegion, dataResidency);
            if (!decision.allowed()) {
                throw new CasExceptions.CasAccessDeniedException(decision.reason(), decision.detail());
            }
            CasStore store = requireStore(readerRegion);
            if (store.contains(digest)) {
                return store.get(digest);
            }
            Placement placement = policy.place(dataResidency);
            // Falling back to the primary is allowed only because the read was already admitted
            // for this residency; the reader's region is inside the permitted set.
            return requireStore(placement.primaryRegion()).get(digest);
        }

        public int replicate() {
            int copied = 0;
            for (Map.Entry<CasDigest, List<String>> entry : new LinkedHashMap<>(replicationBacklog).entrySet()) {
                CasDigest digest = entry.getKey();
                List<String> remaining = new ArrayList<>();
                for (String region : entry.getValue()) {
                    CasStore target = requireStore(region);
                    if (target.contains(digest)) {
                        continue;
                    }
                    byte[] content = findSource(digest);
                    if (content == null) {
                        remaining.add(region);
                        continue;
                    }
                    target.put(digest, content);
                    copied++;
                }
                if (remaining.isEmpty()) {
                    replicationBacklog.remove(digest);
                } else {
                    replicationBacklog.put(digest, remaining);
                }
            }
            return copied;
        }

        public Map<CasDigest, List<String>> outstandingReplication() {
            return Collections.unmodifiableMap(new LinkedHashMap<>(replicationBacklog));
        }

        private byte[] findSource(CasDigest digest) {
            for (CasStore store : storesByRegion.values()) {
                if (store.contains(digest)) {
                    return store.get(digest);
                }
            }
            return null;
        }

        private CasStore requireStore(String region) {
            CasStore store = storesByRegion.get(region);
            if (store == null) {
                throw new IllegalStateException("no store configured for region " + region);
            }
            return store;
        }
    }
}
