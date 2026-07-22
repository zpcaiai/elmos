package io.elmos.developerworkflow;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.developerworkflow.WorkflowModels.*;
import static org.junit.jupiter.api.Assertions.*;

class DeveloperWorkflowCoreTest {
    private static final String DIGEST=Digests.sha256("artifact");

    @Test void ideProtocolAllowsOnlyPinnedScopedRequests() {
        IdeProtocolGateway gateway=gateway();
        var allowed=gateway.authorize(request("src/Order.java","migration-cli",Set.of("migration.preview"),DIGEST));
        assertEquals(Decision.ALLOW,allowed.decision());
        assertEquals("IDE_REQUEST_AUTHORIZED",allowed.code());
    }

    @Test void ideProtocolRejectsTraversalUnknownToolsAndStaleArtifacts() {
        IdeProtocolGateway gateway=gateway();
        assertEquals("PATH_OUTSIDE_WORKSPACE",gateway.authorize(request("../secret","migration-cli",Set.of("migration.preview"),DIGEST)).code());
        assertEquals("TOOL_NOT_ALLOWLISTED",gateway.authorize(request("src/A.java","bash",Set.of("migration.preview"),DIGEST)).code());
        assertEquals("ARTIFACT_DIGEST_REQUIRED",gateway.authorize(request("src/A.java","migration-cli",Set.of("migration.preview"),"latest")).code());
    }

    @Test void sourceTargetNavigationIsBidirectionalManyToManyAndFresh() {
        SourceNode source=new SourceNode("s","source","src/A.java",1,4,DIGEST);
        SourceNode target1=new SourceNode("t1","target","src/A.cs",1,5,DIGEST);
        SourceNode target2=new SourceNode("t2","target","src/AValidator.cs",1,5,DIGEST);
        var navigator=new SourceTargetNavigator(DIGEST,DIGEST,List.of(source,target1,target2),List.of(
                new SourceEdge("s","t1","split",1,List.of("evidence/map.json")),
                new SourceEdge("s","t2","split",.97,List.of("evidence/map.json"))));
        assertEquals(2,navigator.navigate("s",DIGEST,DIGEST,.95).destinations().size());
        assertEquals("NAVIGATION_RESOLVED",navigator.navigate("t1",DIGEST,DIGEST,.95).code());
        assertEquals("STALE_NAVIGATION_MAP",navigator.navigate("s",Digests.sha256("new"),DIGEST,.95).code());
    }

    @Test void unsafeNavigationPathIsRejectedAtConstruction() {
        assertThrows(IllegalArgumentException.class,()->new SourceTargetNavigator(DIGEST,DIGEST,
                List.of(new SourceNode("s","source","../../secret",1,2,DIGEST)),List.of()));
    }

    @Test void ownershipProtectsHumanRegionsAndRequiresApproval() {
        OwnershipPolicyEngine engine=new OwnershipPolicyEngine(List.of(
                new ProtectedRegion("src/A.java",1,10,Ownership.HUMAN,"alice",false),
                new ProtectedRegion("src/A.java",20,30,Ownership.SHARED,"team",true)));
        assertEquals("HUMAN_REGION_PROTECTED",engine.authorize(new EditRequest("src/A.java",5,5,"bot",false)).code());
        assertEquals(Decision.ALLOW,engine.authorize(new EditRequest("src/A.java",5,5,"alice",false)).decision());
        assertEquals(Decision.ESCALATE,engine.authorize(new EditRequest("src/A.java",25,25,"bot",false)).decision());
    }

    @Test void localPreviewIsDeterministicAndNeverWrites() {
        LocalPreviewEngine engine=new LocalPreviewEngine();
        PreviewRequest request=new PreviewRequest(DIGEST,DIGEST,DIGEST,DIGEST,"a\nb","a\nc",false,false);
        PreviewResult first=engine.preview(request), second=engine.preview(request);
        assertEquals(Decision.ALLOW,first.decision()); assertFalse(first.repositoryWritten());
        assertEquals(first.diffDigest(),second.diffDigest()); assertEquals(1,first.changedLines());
    }

    @Test void localPreviewRejectsNetworkAndRepositoryWrites() {
        LocalPreviewEngine engine=new LocalPreviewEngine();
        assertEquals("PREVIEW_REPOSITORY_WRITE_DENIED",engine.preview(new PreviewRequest(DIGEST,DIGEST,DIGEST,DIGEST,"a","b",true,false)).code());
        assertEquals("PREVIEW_NETWORK_DENIED",engine.preview(new PreviewRequest(DIGEST,DIGEST,DIGEST,DIGEST,"a","b",false,true)).code());
    }

    @Test void workflowComposesProtocolOwnershipAndPreview() {
        var service=new DeveloperWorkflowService(gateway(),new OwnershipPolicyEngine(List.of(
                new ProtectedRegion("src/Order.java",1,10,Ownership.GENERATED,"migration-engine",false))),new LocalPreviewEngine());
        var result=service.preview(request("src/Order.java","migration-cli",Set.of("migration.preview"),DIGEST),
                new EditRequest("src/Order.java",2,2,"migration-engine",false),
                new PreviewRequest(DIGEST,DIGEST,DIGEST,DIGEST,"old","new",false,false));
        assertEquals(Decision.ALLOW,result.decision()); assertEquals("PREVIEW_READY",result.code());
    }

    private IdeProtocolGateway gateway() {
        return new IdeProtocolGateway("1.0.0",Set.of("migration-cli"),Map.of("migration.preview","migration.preview"));
    }
    private ProtocolRequest request(String path,String tool,Set<String> permissions,String digest) {
        return new ProtocolRequest("1.0.0","tenant-a","project-a","migration.preview",path,tool,permissions,1,digest);
    }
}
