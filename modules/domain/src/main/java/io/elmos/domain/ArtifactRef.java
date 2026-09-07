package io.elmos.domain;
public record ArtifactRef(String value) { public ArtifactRef { value = Identifiers.require(value, "artifactRef"); } }

