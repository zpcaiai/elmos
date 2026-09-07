package io.elmos.developerworkflow;

import java.util.List;

import static io.elmos.developerworkflow.WorkflowModels.*;

public final class DeveloperWorkflowService {
    private final IdeProtocolGateway protocol;
    private final OwnershipPolicyEngine ownership;
    private final LocalPreviewEngine preview;

    public DeveloperWorkflowService(IdeProtocolGateway protocol, OwnershipPolicyEngine ownership, LocalPreviewEngine preview) {
        this.protocol=protocol; this.ownership=ownership; this.preview=preview;
    }

    public record WorkflowResult(Decision decision, String code, PreviewResult preview, List<String> evidence) {
        public WorkflowResult { evidence=List.copyOf(evidence); }
    }

    public WorkflowResult preview(ProtocolRequest protocolRequest, EditRequest editRequest, PreviewRequest previewRequest) {
        PolicyDecision protocolDecision=protocol.authorize(protocolRequest);
        if (protocolDecision.decision()!=Decision.ALLOW) return new WorkflowResult(protocolDecision.decision(),protocolDecision.code(),null,protocolDecision.evidence());
        PolicyDecision ownershipDecision=ownership.authorize(editRequest);
        if (ownershipDecision.decision()!=Decision.ALLOW) return new WorkflowResult(ownershipDecision.decision(),ownershipDecision.code(),null,ownershipDecision.evidence());
        PreviewResult result=preview.preview(previewRequest);
        return new WorkflowResult(result.decision(),result.code(),result,result.evidence());
    }
}
