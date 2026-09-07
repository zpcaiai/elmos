package io.elmos.domain;

public record Repository(RepositoryId id, OrganizationId organizationId, String scmProvider, String externalId, String defaultBranch) {
    public Repository { if (id == null || organizationId == null) throw new IllegalArgumentException("repository ids are required"); scmProvider = Identifiers.require(scmProvider, "scmProvider"); externalId = Identifiers.require(externalId, "externalId"); defaultBranch = Identifiers.require(defaultBranch, "defaultBranch"); }
}

