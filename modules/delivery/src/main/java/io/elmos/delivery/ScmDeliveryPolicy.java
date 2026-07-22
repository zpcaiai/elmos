package io.elmos.delivery;

import io.elmos.delivery.DeliveryModels.*;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public final class ScmDeliveryPolicy {
    public ScmDeliveryPlan plan(ScmProvider provider, String repository, String migrationId,
                                String baseBranch, String headSha, String title, String body,
                                List<String> reviewers) {
        String branch = ("elmos/" + migrationId).toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9/_-]", "-")
                .replaceAll("-+", "-").replaceAll("^[-/]+|[-/]+$", "");
        String idempotency = DeliveryReadModel.hash(provider + "\n" + repository + "\n" + migrationId + "\n" + headSha);
        return new ScmDeliveryPlan("scm-" + idempotency.substring(0, 24), provider, repository, branch, baseBranch,
                headSha, title, body, true, false, false, reviewers, idempotency);
    }

    public CheckPublication check(ScmProvider provider, GitLabTier tier, String name, String boundHeadSha,
                                  String currentHeadSha, CheckConclusion requested, List<Annotation> annotations,
                                  String summary) {
        boolean stale = !boundHeadSha.equals(currentHeadSha);
        CheckTransport transport = provider == ScmProvider.GITHUB ? CheckTransport.GITHUB_CHECK_RUN
                : tier == GitLabTier.ULTIMATE ? CheckTransport.GITLAB_EXTERNAL_STATUS : CheckTransport.GITLAB_COMMIT_STATUS;
        List<List<Annotation>> batches = new ArrayList<>();
        int maximum = provider == ScmProvider.GITHUB ? 50 : 100;
        for (int index = 0; index < annotations.size(); index += maximum)
            batches.add(List.copyOf(annotations.subList(index, Math.min(annotations.size(), index + maximum))));
        String id = DeliveryReadModel.hash(provider + "\n" + name + "\n" + boundHeadSha).substring(0, 24);
        return new CheckPublication("check-" + id, provider, transport, name, boundHeadSha,
                stale ? CheckConclusion.STALE : requested, batches, summary, stale);
    }
}
