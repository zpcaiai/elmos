package io.elmos.domain;
public record SnapshotId(String value) { public SnapshotId { value = Identifiers.require(value, "snapshotId"); } public static SnapshotId random() { return new SnapshotId(Identifiers.random()); } }

