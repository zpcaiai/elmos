package io.elmos.marketplace;

import java.nio.charset.StandardCharsets;
import java.util.Set;
import static io.elmos.marketplace.MarketplaceModels.*;

public final class MarketplaceCli {
    private MarketplaceCli() {}
    public static void main(String[] args) {
        if (args.length!=1 || !(args[0].equals("inspect") || args[0].equals("evaluate"))) {
            System.err.println("usage: MarketplaceCli <inspect|evaluate>"); System.exit(2);
        }
        String digest=Digests.sha256("elmos-batch37-local-rehearsal".getBytes(StandardCharsets.UTF_8));
        if (args[0].equals("inspect")) {
            System.out.println("{\"schema_version\":1,\"command\":\"inspect\",\"status\":\"READY\",\"external_operation_executed\":false,\"network_access\":false,\"runtime_digest\":\""+digest+"\"}"); return;
        }
        ExtensionManifest manifest=new ExtensionManifest("elmos.local.extension","elmos","0.1.0","0.1.0",digest,"local-tenant",Set.of("artifact:read"),Set.of("extension.evaluate"));
        PolicyDecision decision=new ExtensionManifestValidator().validate(manifest);
        System.out.println("{\"schema_version\":1,\"command\":\"evaluate\",\"decision\":\""+decision.decision()+"\",\"code\":\""+decision.code()+"\",\"certified\":false,\"production_operation_executed\":false,\"release_digest\":\""+digest+"\"}");
        if (decision.decision()!=Decision.ALLOW) System.exit(3);
    }
}
