package io.elmos.portfolio;

import java.util.HashMap;
import java.util.Map;

import static io.elmos.portfolio.PortfolioScaleModels.requireText;

public final class HierarchicalBudgetLedger {
    public enum ReservationStatus { RESERVED, COMMITTED, RELEASED, REJECTED }
    public record Scope(String tenantId, String campaignId) {
        public Scope { requireText(tenantId, "budget tenant"); requireText(campaignId, "budget campaign"); }
    }
    public record Reservation(String idempotencyKey, Scope scope, long units, ReservationStatus status, String reason) {}

    private final Map<Scope, Long> limits = new HashMap<>();
    private final Map<Scope, Long> committed = new HashMap<>();
    private final Map<String, Reservation> reservations = new HashMap<>();

    public void setLimit(Scope scope, long units) {
        if (units < committed.getOrDefault(scope, 0L)) throw new IllegalArgumentException("limit is below committed spend");
        limits.put(scope, units);
    }

    public Reservation reserve(Scope scope, String idempotencyKey, long units) {
        requireText(idempotencyKey, "budget idempotency key");
        if (units < 1) throw new IllegalArgumentException("reservation units must be positive");
        String key=scoped(scope,idempotencyKey); Reservation prior=reservations.get(key);
        if (prior != null) {
            if (prior.units()!=units) throw new IllegalStateException("budget idempotency key reused with different amount");
            return prior;
        }
        long limit=limits.getOrDefault(scope,0L); long held=reservations.values().stream()
                .filter(item -> item.scope().equals(scope) && item.status()==ReservationStatus.RESERVED)
                .mapToLong(Reservation::units).sum();
        if (committed.getOrDefault(scope,0L)+held+units>limit) {
            Reservation rejected=new Reservation(idempotencyKey,scope,units,ReservationStatus.REJECTED,"HARD_BUDGET_LIMIT");
            reservations.put(key,rejected); return rejected;
        }
        Reservation reserved=new Reservation(idempotencyKey,scope,units,ReservationStatus.RESERVED,null);
        reservations.put(key,reserved); return reserved;
    }

    public Reservation commit(Scope scope, String idempotencyKey) {
        String key=scoped(scope,idempotencyKey); Reservation prior=require(key);
        if (prior.status()==ReservationStatus.COMMITTED) return prior;
        if (prior.status()!=ReservationStatus.RESERVED) throw new IllegalStateException("only a reserved budget can be committed");
        Reservation result=new Reservation(idempotencyKey,scope,prior.units(),ReservationStatus.COMMITTED,null);
        reservations.put(key,result); committed.merge(scope,prior.units(),Long::sum); return result;
    }

    public Reservation release(Scope scope, String idempotencyKey) {
        String key=scoped(scope,idempotencyKey); Reservation prior=require(key);
        if (prior.status()==ReservationStatus.RELEASED) return prior;
        if (prior.status()!=ReservationStatus.RESERVED) throw new IllegalStateException("only a reserved budget can be released");
        Reservation result=new Reservation(idempotencyKey,scope,prior.units(),ReservationStatus.RELEASED,null);
        reservations.put(key,result); return result;
    }

    public long committedUnits(Scope scope) { return committed.getOrDefault(scope,0L); }
    private Reservation require(String key) { Reservation result=reservations.get(key); if (result==null) throw new IllegalArgumentException("unknown reservation"); return result; }
    private static String scoped(Scope scope,String key) { return scope.tenantId()+"\0"+scope.campaignId()+"\0"+key; }
}
