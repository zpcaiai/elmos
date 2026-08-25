package io.elmos.scm;

import org.junit.jupiter.api.Test;
import java.time.Instant;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class GitHubPolicyTest {
    @Test void permitsOnlyNamespacedNonForceBranches() {
        var policy = new GitHubBranchWritePolicy();
        policy.authorize("refs/heads/elmos/migration/run-1", "main", false, false, false);
        assertThrows(SecurityException.class, () -> policy.authorize("refs/heads/main", "main", false, false, false));
        assertThrows(SecurityException.class, () -> policy.authorize("feature/backdoor", "main", false, false, false));
        assertThrows(SecurityException.class, () -> policy.authorize("elmos/migration/run", "main", true, false, false));
    }

    @Test void preventsCrossTenantBindingAndSuspendedUse() {
        Map<Long, GitHubInstallationLifecycleService.Installation> installations = new HashMap<>();
        var store = new GitHubInstallationLifecycleService.Store() {
            public boolean bindIfUnclaimed(GitHubInstallationLifecycleService.Installation value) { return installations.putIfAbsent(value.githubInstallationId(), value) == null; }
            public GitHubInstallationLifecycleService.Installation findByExternalId(String organization, long id) {
                var installation = installations.get(id);
                return installation != null && installation.organizationId().equals(organization)
                        ? installation : null;
            }
            public void updateStatus(String organization, long id,
                                     GitHubInstallationLifecycleService.Status status, Instant changed) {
                var old = findByExternalId(organization, id);
                if (old == null) throw new SecurityException("installation is not tenant-owned");
                installations.put(id, new GitHubInstallationLifecycleService.Installation(old.installationId(), old.connectionId(), old.organizationId(),
                        old.githubInstallationId(), old.accountExternalId(), old.accountLogin(), old.targetType(), old.repositorySelection(), old.permissions(), status, old.installedAt(), changed));
            }
            public void replaceAuthorizedRepositories(String organization, long id,
                    Set<GitHubInstallationLifecycleService.Repository> repositories, Instant at) {}
        };
        var service = new GitHubInstallationLifecycleService(store); Instant now = Instant.parse("2026-07-20T00:00:00Z");
        Map<String,String> permissions = Map.of("metadata","read","contents","read");
        service.bind(new GitHubInstallationLifecycleService.Installation("i1","c1","org1",9,1,"example","Organization","selected",permissions, GitHubInstallationLifecycleService.Status.ACTIVE,now,now));
        assertThrows(SecurityException.class, () -> service.bind(new GitHubInstallationLifecycleService.Installation("i2","c2","org2",9,1,"example","Organization","selected",permissions, GitHubInstallationLifecycleService.Status.ACTIVE,now,now)));
        assertThrows(SecurityException.class, () -> service.bind(new GitHubInstallationLifecycleService.Installation(
                "i3","c3","org1",10,1,"example","Organization","selected",
                Map.of("metadata","read"), GitHubInstallationLifecycleService.Status.ACTIVE,now,now)));
        service.suspend("org1", 9, now.plusSeconds(1));
        assertThrows(SecurityException.class, () -> service.requireActive("org1", 9));
        assertThrows(SecurityException.class,
                () -> service.suspend("org2", 9, now.plusSeconds(2)));
    }
}
