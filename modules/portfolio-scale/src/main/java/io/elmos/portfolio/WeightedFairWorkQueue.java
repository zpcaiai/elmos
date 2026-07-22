package io.elmos.portfolio;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static io.elmos.portfolio.PortfolioScaleModels.requireText;

public final class WeightedFairWorkQueue {
    public record TenantPolicy(int weight, int maximumPerDispatch) {
        public TenantPolicy { if (weight<1 || maximumPerDispatch<1) throw new IllegalArgumentException("invalid tenant queue policy"); }
    }
    public record QueueItem(String id, String tenantId, int priority, long enqueuedTick) {
        public QueueItem {
            requireText(id,"queue item id"); requireText(tenantId,"queue tenant");
            if (priority<0 || priority>3 || enqueuedTick<0) throw new IllegalArgumentException("invalid queue priority or tick");
        }
    }

    private final Map<String,TenantPolicy> policies;
    private final Map<String,List<QueueItem>> queues=new HashMap<>();
    private final Map<String,Integer> dispatched=new HashMap<>();
    private final long agingInterval;

    public WeightedFairWorkQueue(Map<String,TenantPolicy> policies,long agingInterval) {
        this.policies=Map.copyOf(policies); if (policies.isEmpty() || agingInterval<1) throw new IllegalArgumentException("queue policy and aging interval are required");
        this.agingInterval=agingInterval;
    }
    public void enqueue(QueueItem item) {
        if (!policies.containsKey(item.tenantId())) throw new IllegalArgumentException("tenant has no queue policy");
        if (queues.values().stream().flatMap(List::stream).anyMatch(existing -> existing.id().equals(item.id()))) throw new IllegalArgumentException("duplicate queue item");
        queues.computeIfAbsent(item.tenantId(),ignored -> new ArrayList<>()).add(item);
    }
    public List<QueueItem> dispatch(int maximum,long currentTick) {
        if (maximum<1) throw new IllegalArgumentException("dispatch maximum must be positive");
        Map<String,Integer> inBatch=new HashMap<>(); List<QueueItem> result=new ArrayList<>();
        while (result.size()<maximum) {
            String tenant=queues.entrySet().stream().filter(entry -> !entry.getValue().isEmpty())
                    .filter(entry -> inBatch.getOrDefault(entry.getKey(),0)<policies.get(entry.getKey()).maximumPerDispatch())
                    .min(Comparator.<Map.Entry<String,List<QueueItem>>>comparingDouble(entry -> dispatched.getOrDefault(entry.getKey(),0)/(double)policies.get(entry.getKey()).weight())
                            .thenComparing(Map.Entry::getKey)).map(Map.Entry::getKey).orElse(null);
            if (tenant==null) break;
            List<QueueItem> queue=queues.get(tenant);
            QueueItem selected=queue.stream().max(Comparator.comparingLong((QueueItem item) -> effectivePriority(item,currentTick))
                    .thenComparingLong(item -> -item.enqueuedTick()).thenComparing(QueueItem::id,Comparator.reverseOrder())).orElseThrow();
            queue.remove(selected); result.add(selected); dispatched.merge(tenant,1,Integer::sum); inBatch.merge(tenant,1,Integer::sum);
        }
        return result;
    }
    private long effectivePriority(QueueItem item,long currentTick) {
        long waited=Math.max(0,currentTick-item.enqueuedTick()); return item.priority()+waited/agingInterval;
    }
}
