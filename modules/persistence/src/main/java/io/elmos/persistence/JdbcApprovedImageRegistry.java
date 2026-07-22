package io.elmos.persistence;

import io.elmos.workspace.WorkspaceInfrastructurePorts;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public final class JdbcApprovedImageRegistry implements WorkspaceInfrastructurePorts.ApprovedImageRegistry {
    private final JdbcClient jdbc;
    public JdbcApprovedImageRegistry(JdbcClient jdbc) { this.jdbc = jdbc; }
    @Override public void requireApproved(String sandboxProfile, String imageDigest) {
        int approved = jdbc.sql("select count(*) from sandbox_profiles where sandbox_profile_id = :profile and image_digest = :digest and approved = true")
                .param("profile", sandboxProfile).param("digest", imageDigest).query(Integer.class).single();
        if (approved != 1) throw new SecurityException("sandbox image digest is not approved");
    }
}
