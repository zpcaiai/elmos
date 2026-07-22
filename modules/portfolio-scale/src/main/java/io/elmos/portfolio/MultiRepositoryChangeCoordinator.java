package io.elmos.portfolio;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.portfolio.PortfolioScaleModels.requireText;

public final class MultiRepositoryChangeCoordinator {
    public enum ChangeStatus { OPEN, READY, MERGED, FAILED, ROLLED_BACK }
    public record Change(String id, String repositoryId, List<String> dependsOn,
                         Set<String> requiredChecks, Set<String> passedChecks,
                         int requiredApprovals, int grantedApprovals,
                         boolean rollbackPrepared, ChangeStatus status) {
        public Change {
            requireText(id,"change id"); requireText(repositoryId,"change repository");
            dependsOn=List.copyOf(dependsOn); requiredChecks=Set.copyOf(requiredChecks); passedChecks=Set.copyOf(passedChecks);
            if (requiredApprovals<0 || grantedApprovals<0) throw new IllegalArgumentException("invalid approval count");
        }
    }
    public record MergeDecision(boolean allowed,List<String> blockers) { public MergeDecision { blockers=List.copyOf(blockers); } }

    private final Map<String,Change> changes=new HashMap<>();
    private final Map<String,String> mergeTokens=new HashMap<>();
    public void register(Change change) {
        if (changes.putIfAbsent(change.id(),change)!=null) throw new IllegalArgumentException("duplicate change");
    }
    public void update(Change change) {
        Change prior=require(change.id());
        if (!prior.repositoryId().equals(change.repositoryId()) || !prior.dependsOn().equals(change.dependsOn())
                || !prior.requiredChecks().equals(change.requiredChecks()) || prior.requiredApprovals()!=change.requiredApprovals()
                || prior.rollbackPrepared()!=change.rollbackPrepared()) {
            throw new IllegalArgumentException("immutable change scope or safeguards were modified");
        }
        if (prior.status()==ChangeStatus.MERGED || prior.status()==ChangeStatus.ROLLED_BACK) throw new IllegalStateException("terminal change cannot be updated");
        changes.put(change.id(),change);
    }
    public MergeDecision evaluate(String changeId) {
        Change change=require(changeId); List<String> blockers=new ArrayList<>();
        if (change.status()!=ChangeStatus.OPEN && change.status()!=ChangeStatus.READY) blockers.add("CHANGE_NOT_OPEN:"+change.status());
        if (!change.passedChecks().containsAll(change.requiredChecks())) blockers.add("REQUIRED_CHECKS_MISSING");
        if (change.grantedApprovals()<change.requiredApprovals()) blockers.add("APPROVALS_MISSING");
        if (!change.rollbackPrepared()) blockers.add("ROLLBACK_NOT_PREPARED");
        for (String dependency:change.dependsOn()) {
            Change parent=changes.get(dependency);
            if (parent==null) blockers.add("UNKNOWN_DEPENDENCY:"+dependency);
            else if (parent.status()!=ChangeStatus.MERGED) blockers.add("DEPENDENCY_NOT_MERGED:"+dependency);
        }
        return new MergeDecision(blockers.isEmpty(),blockers);
    }
    public Change merge(String changeId,String commitToken) {
        requireText(commitToken,"merge commit token"); Change change=require(changeId); String prior=mergeTokens.get(changeId);
        if (prior!=null) {
            if (!prior.equals(commitToken)) throw new IllegalStateException("change already merged with another commit token");
            return changes.get(changeId);
        }
        MergeDecision decision=evaluate(changeId); if (!decision.allowed()) throw new IllegalStateException("merge blocked: "+decision.blockers());
        Change merged=new Change(change.id(),change.repositoryId(),change.dependsOn(),change.requiredChecks(),change.passedChecks(),
                change.requiredApprovals(),change.grantedApprovals(),change.rollbackPrepared(),ChangeStatus.MERGED);
        changes.put(changeId,merged); mergeTokens.put(changeId,commitToken); return merged;
    }
    public Change failAndRollback(String changeId) {
        Change change=require(changeId); if (!change.rollbackPrepared()) throw new IllegalStateException("rollback is not prepared");
        Change rolledBack=new Change(change.id(),change.repositoryId(),change.dependsOn(),change.requiredChecks(),change.passedChecks(),
                change.requiredApprovals(),change.grantedApprovals(),true,ChangeStatus.ROLLED_BACK);
        changes.put(changeId,rolledBack); return rolledBack;
    }
    private Change require(String id) { Change result=changes.get(id); if (result==null) throw new IllegalArgumentException("unknown change: "+id); return result; }
}
