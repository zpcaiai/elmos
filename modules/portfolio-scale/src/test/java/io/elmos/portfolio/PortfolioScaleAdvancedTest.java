package io.elmos.portfolio;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class PortfolioScaleAdvancedTest {
    @Test void semanticIndexIsTenantAclBaselineAndVersionIsolated() {
        TenantSemanticIndex index=new TenantSemanticIndex();
        var a1=doc("tenant-a","doc-1","base-a","Order.Service",1,Set.of("team-a"),false);
        var b1=doc("tenant-b","doc-1","base-a","Order.Secret",1,Set.of("team-b"),false);
        index.upsert(a1); index.upsert(b1);
        assertEquals(List.of(a1),index.query("tenant-a","team-a","base-a","Order"));
        assertTrue(index.query("tenant-a","team-b","base-a","Order").isEmpty());
        assertThrows(IllegalArgumentException.class,()->index.upsert(a1));
        var tombstone=doc("tenant-a","doc-1","base-a","Order.Service",2,Set.of("team-a"),true);
        index.upsert(tombstone); assertTrue(index.query("tenant-a","team-a","base-a","Order").isEmpty());
        TenantSemanticIndex rebuilt=TenantSemanticIndex.rebuild(List.of(a1,b1,tombstone));
        assertEquals(index.snapshotDigest("tenant-a"),rebuilt.snapshotDigest("tenant-a"));
    }

    @Test void artifactTransferIsRegionalChunkedResumableAndTenantScoped() {
        byte[] artifact="abcdefghij".getBytes(StandardCharsets.UTF_8);
        ResumableArtifactTransfer transfer=new ResumableArtifactTransfer(
                Set.of(new ResumableArtifactTransfer.RegionRoute("cn-east","cn-north")),100);
        var manifest=transfer.begin("transfer-1","tenant-a","cn-east","cn-north",artifact,4,true);
        assertEquals(List.of(0,1,2),transfer.missingChunks("tenant-a","transfer-1"));
        transfer.uploadChunk("tenant-a","transfer-1",1,Arrays.copyOfRange(artifact,4,8));
        transfer.uploadChunk("tenant-a","transfer-1",0,Arrays.copyOfRange(artifact,0,4));
        assertEquals(List.of(2),transfer.missingChunks("tenant-a","transfer-1"));
        assertThrows(SecurityException.class,()->transfer.missingChunks("tenant-b","transfer-1"));
        assertThrows(IllegalArgumentException.class,()->transfer.uploadChunk("tenant-a","transfer-1",2,"bad".getBytes(StandardCharsets.UTF_8)));
        transfer.uploadChunk("tenant-a","transfer-1",2,Arrays.copyOfRange(artifact,8,10));
        assertArrayEquals(artifact,transfer.complete("tenant-a","transfer-1"));
        assertEquals(manifest,transfer.begin("transfer-1","tenant-a","cn-east","cn-north",artifact,4,true));
        assertThrows(SecurityException.class,()->transfer.begin("x","tenant-a","cn-east","eu-west",artifact,4,true));
        assertThrows(SecurityException.class,()->transfer.begin("x","tenant-a","cn-east","cn-north",artifact,4,false));
    }

    @Test void hierarchicalBudgetReservationsAreBoundedAndIdempotent() {
        HierarchicalBudgetLedger ledger=new HierarchicalBudgetLedger();
        var scope=new HierarchicalBudgetLedger.Scope("tenant-a","campaign-a"); ledger.setLimit(scope,10);
        var reserved=ledger.reserve(scope,"idem-1",7); assertEquals(HierarchicalBudgetLedger.ReservationStatus.RESERVED,reserved.status());
        assertEquals(reserved,ledger.reserve(scope,"idem-1",7));
        assertThrows(IllegalStateException.class,()->ledger.reserve(scope,"idem-1",8));
        assertEquals(HierarchicalBudgetLedger.ReservationStatus.REJECTED,ledger.reserve(scope,"idem-2",4).status());
        assertEquals(HierarchicalBudgetLedger.ReservationStatus.COMMITTED,ledger.commit(scope,"idem-1").status());
        assertEquals(7,ledger.committedUnits(scope));
        assertEquals(HierarchicalBudgetLedger.ReservationStatus.RESERVED,ledger.reserve(scope,"idem-3",3).status());
        assertEquals(HierarchicalBudgetLedger.ReservationStatus.RELEASED,ledger.release(scope,"idem-3").status());
    }

    @Test void weightedQueuePreventsNoisyNeighborAndAgesWaitingWork() {
        WeightedFairWorkQueue queue=new WeightedFairWorkQueue(Map.of(
                "tenant-a",new WeightedFairWorkQueue.TenantPolicy(1,2),
                "tenant-b",new WeightedFairWorkQueue.TenantPolicy(1,2)),5);
        queue.enqueue(new WeightedFairWorkQueue.QueueItem("a-high","tenant-a",3,10));
        queue.enqueue(new WeightedFairWorkQueue.QueueItem("a-new","tenant-a",3,20));
        queue.enqueue(new WeightedFairWorkQueue.QueueItem("b-old","tenant-b",0,0));
        List<WeightedFairWorkQueue.QueueItem> first=queue.dispatch(2,20);
        assertEquals(Set.of("tenant-a","tenant-b"),Set.of(first.get(0).tenantId(),first.get(1).tenantId()));
        assertTrue(first.stream().anyMatch(item->item.id().equals("b-old")));
        assertEquals(List.of("a-new"),queue.dispatch(2,20).stream().map(WeightedFairWorkQueue.QueueItem::id).toList());
    }

    @Test void controlTowerKeepsUnknownAndStaleScopeInDenominatorAndForecastsRanges() {
        PortfolioControlTower tower=new PortfolioControlTower();
        tower.observe(new PortfolioControlTower.Observation("wu-1","repo-1",PortfolioControlTower.WorkState.SUCCEEDED,100,3,List.of("e1")));
        tower.observe(new PortfolioControlTower.Observation("wu-2","repo-2",PortfolioControlTower.WorkState.FAILED,195,5,List.of("e2")));
        var snapshot=tower.snapshot(200,50,3);
        assertEquals(3,snapshot.total()); assertEquals(1,snapshot.succeeded()); assertEquals(1,snapshot.failed());
        assertEquals(1,snapshot.unknown()); assertEquals(1,snapshot.stale()); assertFalse(snapshot.trustworthy());
        var forecast=tower.forecast(List.of(8L,10L,12L,20L),8,2);
        assertTrue(forecast.earliestDurationUnits()<=forecast.likelyDurationUnits());
        assertTrue(forecast.likelyDurationUnits()<=forecast.latestDurationUnits());
        assertTrue(forecast.confidence()>0 && forecast.confidence()<1);
        assertEquals(Long.MAX_VALUE,tower.forecast(List.of(),1,1).latestDurationUnits());
    }

    @Test void multiRepositoryChangesHonorChecksApprovalsOrderRollbackAndCommitTokens() {
        MultiRepositoryChangeCoordinator coordinator=new MultiRepositoryChangeCoordinator();
        var provider=change("provider",List.of(),Set.of("build"),Set.of("build"),1,1,true);
        var consumer=change("consumer",List.of("provider"),Set.of("build","contract"),Set.of("build"),2,1,true);
        coordinator.register(provider); coordinator.register(consumer);
        assertFalse(coordinator.evaluate("consumer").allowed());
        assertEquals(MultiRepositoryChangeCoordinator.ChangeStatus.MERGED,coordinator.merge("provider","commit-provider").status());
        assertFalse(coordinator.evaluate("consumer").allowed());
        assertThrows(IllegalStateException.class,()->coordinator.merge("consumer","commit-consumer"));
        coordinator.update(change("consumer",List.of("provider"),Set.of("build","contract"),Set.of("build","contract"),2,2,true));
        assertTrue(coordinator.evaluate("consumer").allowed());
        assertEquals(MultiRepositoryChangeCoordinator.ChangeStatus.MERGED,coordinator.merge("consumer","commit-consumer").status());
        assertEquals(MultiRepositoryChangeCoordinator.ChangeStatus.MERGED,coordinator.merge("provider","commit-provider").status());
        assertThrows(IllegalStateException.class,()->coordinator.merge("provider","different-token"));
        assertEquals(MultiRepositoryChangeCoordinator.ChangeStatus.ROLLED_BACK,coordinator.failAndRollback("consumer").status());
    }

    private static TenantSemanticIndex.SemanticDocument doc(String tenant,String id,String baseline,String symbol,long version,Set<String> readers,boolean tombstone) {
        return new TenantSemanticIndex.SemanticDocument(tenant,id,"repo",baseline,symbol,"sha256:"+id+version,version,readers,tombstone);
    }
    private static MultiRepositoryChangeCoordinator.Change change(String id,List<String> deps,Set<String> checks,Set<String> passed,int required,int granted,boolean rollback) {
        return new MultiRepositoryChangeCoordinator.Change(id,"repo-"+id,deps,checks,passed,required,granted,rollback,MultiRepositoryChangeCoordinator.ChangeStatus.OPEN);
    }
}
