package io.elmos.cas;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

import static org.junit.jupiter.api.Assertions.*;

class CasBatchAndPlacementTest {

    private final AtomicLong clock = new AtomicLong(1_000);

    private static byte[] bytes(String text) {
        return text.getBytes(StandardCharsets.UTF_8);
    }

    private static CasBatch.WriteItem item(String text) {
        return new CasBatch.WriteItem(CasDigest.of(bytes(text)), bytes(text));
    }

    @Test void batchWriteSkipsObjectsTheStoreAlreadyHolds() {
        InMemoryCasStore store = new InMemoryCasStore("l2");
        store.put(CasDigest.of(bytes("a")), bytes("a"));

        var result = store.putAll(List.of(item("a"), item("b"), item("c")));
        assertEquals(List.of(CasDigest.of(bytes("b")), CasDigest.of(bytes("c"))), result.written());
        assertEquals(List.of(CasDigest.of(bytes("a"))), result.skippedAlreadyPresent());
        assertTrue(result.complete());
        assertEquals(1, result.bytesSkipped());
    }

    @Test void aDuplicateInsideOneBatchIsSentOnlyOnce() {
        InMemoryCasStore store = new InMemoryCasStore("l2");
        var result = store.putAll(List.of(item("x"), item("x"), item("y")));
        assertEquals(List.of(CasDigest.of(bytes("x")), CasDigest.of(bytes("y"))), result.written());
        assertEquals(List.of(CasDigest.of(bytes("x"))), result.skippedAlreadyPresent());
    }

    @Test void oneBadObjectDoesNotAbortTheRestOfTheBatch() {
        InMemoryCasStore store = new InMemoryCasStore("l2");
        CasDigest lie = CasDigest.of(bytes("declared"));
        var items = new ArrayList<CasBatch.WriteItem>();
        items.add(item("first"));
        items.add(new CasBatch.WriteItem(lie, bytes("actual")));
        items.add(item("third"));

        var result = store.putAll(items);
        assertEquals(List.of(CasDigest.of(bytes("first")), CasDigest.of(bytes("third"))), result.written());
        assertFalse(result.complete());
        assertEquals(1, result.failed().size());
        assertTrue(result.failed().get(lie).startsWith("CasCorruptionException"));
        assertTrue(store.contains(CasDigest.of(bytes("third"))));
    }

    @Test void batchReadReportsMissingObjectsInsteadOfThrowing() {
        InMemoryCasStore store = new InMemoryCasStore("l2");
        store.put(CasDigest.of(bytes("present")), bytes("present"));
        CasDigest absent = CasDigest.of(bytes("absent"));

        var result = store.getAll(List.of(CasDigest.of(bytes("present")), absent, absent));
        assertEquals(1, result.found().size());
        assertArrayEquals(bytes("present"), result.found().get(CasDigest.of(bytes("present"))));
        assertEquals(List.of(absent), result.missing());
        assertFalse(result.complete());
    }

    @Test void batchReadIsolatesAPoisonedObjectFromTheHealthyOnes() {
        InMemoryCasStore store = new InMemoryCasStore("l2");
        CasDigest healthy = CasDigest.of(bytes("healthy"));
        CasDigest poisoned = CasDigest.of(bytes("poisoned"));
        store.put(healthy, bytes("healthy"));
        store.put(poisoned, bytes("poisoned"));
        store.corruptForFaultInjection(poisoned, bytes("tampered"));

        var result = store.getAll(List.of(healthy, poisoned));
        assertEquals(1, result.found().size());
        assertTrue(result.failed().get(poisoned).startsWith("CasCorruptionException"));
    }

    @Test void batchDurablePutReachesTheSharedTierBeforeReturning() {
        InMemoryCasStore local = new InMemoryCasStore("l1");
        InMemoryCasStore shared = new InMemoryCasStore("l2");
        TieredCasStore tiered = new TieredCasStore(local, shared, TieredCasStore.TierPolicy.unbounded(), clock::get);

        var result = tiered.putAllDurable(List.of(item("one"), item("two")));
        assertEquals(2, result.written().size());
        assertTrue(shared.contains(CasDigest.of(bytes("one"))));
        assertTrue(shared.contains(CasDigest.of(bytes("two"))));
        assertTrue(tiered.pendingDurability().isEmpty());
    }

    private static RegionalPlacement.Policy policy() {
        return new RegionalPlacement.Policy()
                .withRule(new RegionalPlacement.PlacementRule("eu-customer-data", "eu-west-1",
                        List.of("eu-central-1"), true))
                .withRule(new RegionalPlacement.PlacementRule("us-customer-data", "us-east-1",
                        List.of(), false))
                .withRule(new RegionalPlacement.PlacementRule("public-dependency", "us-east-1",
                        List.of("eu-west-1", "eu-central-1"), false));
    }

    private static Map<String, CasStore> regionStores() {
        return Map.of("eu-west-1", new InMemoryCasStore("eu-west-1"),
                "eu-central-1", new InMemoryCasStore("eu-central-1"),
                "us-east-1", new InMemoryCasStore("us-east-1"));
    }

    @Test void anUnmappedResidencyIsRefusedRatherThanDefaulted() {
        var error = assertThrows(CasExceptions.CasAccessDeniedException.class,
                () -> policy().place("ap-southeast-2"));
        assertEquals("RESIDENCY_NOT_MAPPED", error.reason());
        assertEquals("RESIDENCY_NOT_MAPPED", policy().admitWrite("us-east-1", "ap-southeast-2").reason());
    }

    @Test void euDataCannotBeWrittenToAUsRegion() {
        var decision = policy().admitWrite("us-east-1", "eu-customer-data");
        assertFalse(decision.allowed());
        assertEquals("REGION_NOT_PERMITTED_FOR_RESIDENCY", decision.reason());
        assertTrue(policy().admitWrite("eu-central-1", "eu-customer-data").allowed());
    }

    @Test void writesLandInThePrimaryRegionAndReplicateWhenRequired() {
        Map<String, CasStore> stores = regionStores();
        var router = new RegionalPlacement.Router(policy(), stores);
        CasDigest digest = CasDigest.of(bytes("eu payload"));

        assertEquals("eu-west-1", router.put("eu-customer-data", digest, bytes("eu payload")));
        assertTrue(stores.get("eu-west-1").contains(digest));
        assertTrue(stores.get("eu-central-1").contains(digest), "replication is required for this residency");
        assertFalse(stores.get("us-east-1").contains(digest));
        assertTrue(router.outstandingReplication().isEmpty());
    }

    @Test void optionalReplicationStaysInTheBacklogUntilItIsDrained() {
        Map<String, CasStore> stores = regionStores();
        var router = new RegionalPlacement.Router(policy(), stores);
        CasDigest digest = CasDigest.of(bytes("maven central jar"));

        router.put("public-dependency", digest, bytes("maven central jar"));
        assertTrue(stores.get("us-east-1").contains(digest));
        assertFalse(stores.get("eu-west-1").contains(digest));
        assertEquals(List.of("eu-west-1", "eu-central-1"), router.outstandingReplication().get(digest));

        assertEquals(2, router.replicate());
        assertTrue(stores.get("eu-west-1").contains(digest));
        assertTrue(router.outstandingReplication().isEmpty());
    }

    @Test void aReaderInAForbiddenRegionIsDeniedEvenWhenTheBytesAreReachable() {
        Map<String, CasStore> stores = regionStores();
        var router = new RegionalPlacement.Router(policy(), stores);
        CasDigest digest = CasDigest.of(bytes("eu payload"));
        router.put("eu-customer-data", digest, bytes("eu payload"));

        var error = assertThrows(CasExceptions.CasAccessDeniedException.class,
                () -> router.get("us-east-1", "eu-customer-data", digest));
        assertEquals("REGION_NOT_PERMITTED_FOR_RESIDENCY", error.reason());
        assertArrayEquals(bytes("eu payload"), router.get("eu-central-1", "eu-customer-data", digest));
    }

    @Test void aRuleThatRequiresReplicationWithoutAReplicaIsRejectedAtConstruction() {
        assertThrows(IllegalArgumentException.class,
                () -> new RegionalPlacement.PlacementRule("x", "r1", List.of(), true));
        assertThrows(IllegalArgumentException.class,
                () -> new RegionalPlacement.PlacementRule("x", "r1", List.of("r1"), false));
    }
}
