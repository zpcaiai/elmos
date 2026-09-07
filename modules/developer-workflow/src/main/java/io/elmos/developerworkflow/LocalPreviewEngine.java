package io.elmos.developerworkflow;

import java.util.List;

import static io.elmos.developerworkflow.WorkflowModels.*;

public final class LocalPreviewEngine {
    public PreviewResult preview(PreviewRequest request) {
        if (request.repositoryWrite()) return denied("PREVIEW_REPOSITORY_WRITE_DENIED");
        if (request.networkAccess()) return denied("PREVIEW_NETWORK_DENIED");
        if (!Digests.exactSha256(request.sourceDigest()) || !Digests.exactSha256(request.targetDigest())
                || !Digests.exactSha256(request.recipeDigest()) || !Digests.exactSha256(request.environmentDigest())) {
            return denied("PINNED_DIGESTS_REQUIRED");
        }
        String before = normalize(request.before());
        String after = normalize(request.after());
        int changed = changedLines(before, after);
        String digest = Digests.sha256(request.sourceDigest() + "\n" + request.targetDigest() + "\n"
                + request.recipeDigest() + "\n" + request.environmentDigest() + "\n" + before + "\n---\n" + after);
        return new PreviewResult(Decision.ALLOW, "PREVIEW_READY", digest, changed, false,
                List.of(request.sourceDigest(), request.targetDigest(), request.recipeDigest(), request.environmentDigest()));
    }

    private static PreviewResult denied(String code) {
        return new PreviewResult(Decision.DENY, code, "", 0, false, List.of());
    }
    private static String normalize(String value) { return value.replace("\r\n", "\n").stripTrailing(); }
    private static int changedLines(String before, String after) {
        String[] left=before.split("\n",-1), right=after.split("\n",-1); int changed=0;
        for (int i=0;i<Math.max(left.length,right.length);i++) if (i>=left.length || i>=right.length || !left[i].equals(right[i])) changed++;
        return changed;
    }
}
