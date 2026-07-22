package io.elmos.domain;
public record RepositoryId(String value) { public RepositoryId { value = Identifiers.require(value, "repositoryId"); } public static RepositoryId random() { return new RepositoryId(Identifiers.random()); } }

