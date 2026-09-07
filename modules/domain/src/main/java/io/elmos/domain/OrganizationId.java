package io.elmos.domain;
public record OrganizationId(String value) { public OrganizationId { value = Identifiers.require(value, "organizationId"); } public static OrganizationId random() { return new OrganizationId(Identifiers.random()); } }

