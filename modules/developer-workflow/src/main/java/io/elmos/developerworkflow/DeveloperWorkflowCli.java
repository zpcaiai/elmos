package io.elmos.developerworkflow;

import java.util.Map;
import java.util.Set;

import static io.elmos.developerworkflow.WorkflowModels.*;

public final class DeveloperWorkflowCli {
    private DeveloperWorkflowCli() {}

    public static void main(String[] args) {
        if (args.length!=1 || !(args[0].equals("inspect") || args[0].equals("preview"))) {
            System.err.println("usage: DeveloperWorkflowCli <inspect|preview>");
            System.exit(2);
        }
        String digest=Digests.sha256("elmos-batch36-local-rehearsal");
        if (args[0].equals("inspect")) {
            System.out.println("{\"schema_version\":1,\"command\":\"inspect\",\"status\":\"READY\",\"network_access\":false,\"repository_write\":false,\"runtime_digest\":\""+digest+"\"}");
            return;
        }
        IdeProtocolGateway gateway=new IdeProtocolGateway("1.0.0",Set.of("migration-cli"),Map.of("migration.preview","migration.preview"));
        OwnershipPolicyEngine ownership=new OwnershipPolicyEngine(java.util.List.of(new ProtectedRegion("src/OrderService.java",1,20,Ownership.GENERATED,"migration-engine",false)));
        DeveloperWorkflowService service=new DeveloperWorkflowService(gateway,ownership,new LocalPreviewEngine());
        ProtocolRequest protocol=new ProtocolRequest("1.0.0","local-tenant","elmos","migration.preview","src/OrderService.java","migration-cli",Set.of("migration.preview"),1,digest);
        PreviewRequest preview=new PreviewRequest(digest,digest,digest,digest,"class Order {}","class Order { String id; }",false,false);
        DeveloperWorkflowService.WorkflowResult result=service.preview(protocol,new EditRequest("src/OrderService.java",2,2,"migration-engine",false),preview);
        System.out.println("{\"schema_version\":1,\"command\":\"preview\",\"decision\":\""+result.decision()+"\",\"code\":\""+result.code()+"\",\"repository_write\":false,\"network_access\":false,\"diff_digest\":\""+(result.preview()==null?"":result.preview().diffDigest())+"\"}");
        if (result.decision()!=Decision.ALLOW) System.exit(3);
    }
}
