package io.elmos.developerworkflow;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.developerworkflow.WorkflowModels.*;
import static org.junit.jupiter.api.Assertions.*;

class DeveloperWorkflowGovernanceTest {
    private static final String DIGEST=Digests.sha256("exact");

    @Test void affectedTestsAreBoundedDeterministicAndEscalateUnknowns() {
        AffectedTestSelector selector=new AffectedTestSelector(Map.of("service",Set.of("repository"),"repository",Set.of()),
                Map.of("service",Set.of("ServiceTest"),"repository",Set.of("RepositoryTest")));
        TestSelection selected=selector.select(Set.of("service"),10,10);
        assertEquals(Decision.ALLOW,selected.decision()); assertEquals(Set.of("ServiceTest","RepositoryTest"),selected.tests());
        assertEquals("UNKNOWN_IMPACT_EDGE",selector.select(Set.of("unknown"),10,10).code());
    }

    @Test void affectedTestBudgetsEscalateToBroaderSuite() {
        AffectedTestSelector selector=new AffectedTestSelector(Map.of("a",Set.of("b"),"b",Set.of()),Map.of("a",Set.of("A"),"b",Set.of("B")));
        TestSelection result=selector.select(Set.of("a"),1,10);
        assertEquals(Decision.ESCALATE,result.decision()); assertTrue(result.evidence().contains("run:broader-suite"));
    }

    @Test void prBotRequiresExactLeastPrivilegeAndReplayProtection() {
        PrBotPolicyEvaluator evaluator=new PrBotPolicyEvaluator();
        PrBotRequest valid=new PrBotRequest("github","check",Set.of("contents:read","pull_requests:write"),"alice","bot",false,false,DIGEST,true,false);
        assertEquals(Decision.ALLOW,evaluator.authorize(valid).decision());
        assertEquals("BOT_SCOPE_NOT_LEAST_PRIVILEGE",evaluator.authorize(new PrBotRequest("github","check",Set.of("contents:write"),"alice","bot",false,false,DIGEST,true,false)).code());
        assertEquals("SCM_EVENT_UNTRUSTED",evaluator.authorize(new PrBotRequest("github","check",valid.tokenScopes(),"alice","bot",false,false,DIGEST,true,true)).code());
    }

    @Test void forkedPullRequestsCannotReceiveSecrets() {
        var result=new PrBotPolicyEvaluator().authorize(new PrBotRequest("github","check",Set.of("contents:read","pull_requests:write"),"alice","bot",true,true,DIGEST,true,false));
        assertEquals("FORK_SECRET_ISOLATION_FAILED",result.code());
    }

    @Test void telemetryRejectsSourceSecretsAndAbsolutePaths() {
        TelemetryPrivacyFilter filter=new TelemetryPrivacyFilter(Set.of("preview.completed"),Set.of("route","duration_bucket"));
        assertEquals(Decision.ALLOW,filter.filter("preview.completed",Map.of("route","java-to-csharp","duration_bucket","1-5s"),true).decision());
        assertEquals("FORBIDDEN_TELEMETRY_FIELD",filter.filter("preview.completed",Map.of("source_code","class A{}"),true).code());
        assertEquals("ABSOLUTE_PATH_FORBIDDEN",filter.filter("preview.completed",Map.of("route","/Users/alice/repo"),true).code());
        assertEquals("TELEMETRY_CONSENT_REQUIRED",filter.filter("preview.completed",Map.of(),false).code());
    }

    @Test void semanticConflictsPreserveHumanWorkAndEscalateAmbiguity() {
        SemanticConflictResolver resolver=new SemanticConflictResolver();
        assertEquals("SAFE_REGENERATION",resolver.resolve(new SemanticConflictResolver.Conflict("base","old","old","new",Ownership.GENERATED,false)).code());
        assertEquals("PRESERVE_HUMAN_EDIT",resolver.resolve(new SemanticConflictResolver.Conflict("base","generated","human","generated",Ownership.SHARED,false)).code());
        assertEquals("AMBIGUOUS_SEMANTIC_CONFLICT",resolver.resolve(new SemanticConflictResolver.Conflict("base","generated","human","new-generated",Ownership.SHARED,false)).code());
        assertEquals("HUMAN_OWNER_DECISION_REQUIRED",resolver.resolve(new SemanticConflictResolver.Conflict("base","generated","human","new-generated",Ownership.HUMAN,false)).code());
    }

    @Test void quickFixBindsDiagnosticRangeArtifactOwnershipAndTests() {
        OwnershipPolicyEngine ownership=new OwnershipPolicyEngine(List.of(new ProtectedRegion("src/A.java",1,20,Ownership.GENERATED,"engine",false)));
        var diagnostic=new DiagnosticQuickFixPlanner.Diagnostic("D1",DIGEST,"src/A.java",5,8);
        var fix=new DiagnosticQuickFixPlanner.FixCandidate("D1",DIGEST,"src/A.java",5,6,DIGEST,Set.of("ATest"));
        assertEquals(Decision.ALLOW,new DiagnosticQuickFixPlanner().plan(diagnostic,fix,ownership,"engine").decision());
        var stale=new DiagnosticQuickFixPlanner.FixCandidate("D1",Digests.sha256("stale"),"src/A.java",5,6,DIGEST,Set.of("ATest"));
        assertEquals("STALE_DIAGNOSTIC_BINDING",new DiagnosticQuickFixPlanner().plan(diagnostic,stale,ownership,"engine").code());
    }

    @Test void recipeAuthoringRejectsScriptsAndRequiresIndependentCorpora() {
        RecipeAuthoringValidator validator=new RecipeAuthoringValidator();
        var unsafe=new RecipeAuthoringValidator.Recipe("r","in","out",List.of("map"),Set.of("compiler"),true,true,true,true);
        assertEquals("ARBITRARY_RECIPE_SCRIPT_DENIED",validator.validate(unsafe,Set.of("compiler")).code());
        var incomplete=new RecipeAuthoringValidator.Recipe("r","in","out",List.of("map"),Set.of("compiler"),false,true,false,true);
        assertEquals(Decision.ESCALATE,validator.validate(incomplete,Set.of("compiler")).decision());
        var ready=new RecipeAuthoringValidator.Recipe("r","in","out",List.of("map"),Set.of("compiler"),false,true,true,true);
        assertEquals(Decision.ALLOW,validator.validate(ready,Set.of("compiler")).decision());
    }

    @Test void approvalsRequireExactScopeIndependenceAndFreshness() {
        ReviewApprovalPolicy policy=new ReviewApprovalPolicy();
        Approval valid=new Approval("alice","bob",DIGEST,DIGEST,200,true);
        assertEquals(Decision.ALLOW,policy.validate(valid,DIGEST,DIGEST,100).decision());
        assertEquals("SEPARATION_OF_DUTIES_REQUIRED",policy.validate(new Approval("alice","alice",DIGEST,DIGEST,200,false),DIGEST,DIGEST,100).code());
        assertEquals("APPROVAL_EXPIRED",policy.validate(valid,DIGEST,DIGEST,201).code());
    }

    @Test void offlineWorkflowCannotCreateRightsOrUseNetwork() {
        OfflineWorkflowVerifier verifier=new OfflineWorkflowVerifier();
        OfflineBundle valid=new OfflineBundle(DIGEST,DIGEST,"root-a",Set.of("root-a"),Set.of("preview"),Set.of("preview","read"),true,false);
        assertEquals(Decision.ALLOW,verifier.verify(valid).decision());
        assertEquals("OFFLINE_NETWORK_MUST_BE_DISABLED",verifier.verify(new OfflineBundle(DIGEST,DIGEST,"root-a",Set.of("root-a"),Set.of(),Set.of(),true,true)).code());
        assertEquals("OFFLINE_PERMISSION_NOT_PREGRANTED",verifier.verify(new OfflineBundle(DIGEST,DIGEST,"root-a",Set.of("root-a"),Set.of("write"),Set.of("read"),true,false)).code());
    }
}
