package io.elmos.domain;
public record CommitSha(String value) {
    public CommitSha { value = Identifiers.require(value, "commitSha").toLowerCase(); if (!value.matches("[0-9a-f]{7,64}")) throw new IllegalArgumentException("commitSha must be hexadecimal"); }
}

