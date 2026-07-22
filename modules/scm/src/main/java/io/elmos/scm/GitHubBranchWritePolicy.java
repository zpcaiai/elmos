package io.elmos.scm;

import java.util.List;

public final class GitHubBranchWritePolicy {
    private static final List<String> PREFIXES = List.of("elmos/assessment/", "elmos/migration/", "elmos/security-fix/");
    public void authorize(String targetRef, String defaultBranch, boolean force, boolean delete, boolean tag) {
        if (targetRef == null || targetRef.isBlank() || defaultBranch == null || defaultBranch.isBlank()) throw new IllegalArgumentException("branch identity is required");
        if (force || delete || tag || targetRef.startsWith("refs/tags/")) throw new SecurityException("force, delete, and tag writes are forbidden");
        String branch = targetRef.startsWith("refs/heads/") ? targetRef.substring("refs/heads/".length()) : targetRef;
        if (branch.equals(defaultBranch)) throw new SecurityException("ELMOS cannot write the default branch");
        if (PREFIXES.stream().noneMatch(branch::startsWith)) throw new SecurityException("branch is outside the ELMOS namespace");
    }
}
