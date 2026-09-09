const ROLES = ["VIEWER", "DEVELOPER", "MAINTAINER", "OPERATOR", "APPROVER", "TENANT_ADMIN"] as const;
export type OrganizationRole = (typeof ROLES)[number];

export class OrganizationError extends Error {
  readonly code: string;
  readonly status: number;
  constructor(code: string, status = 403) {
    super(code);
    this.name = "OrganizationError";
    this.code = code;
    this.status = status;
  }
}

export type OrganizationRecord = {
  organizationId: string;
  name: string;
  createdBy: string;
  members: Record<string, { email: string; role: OrganizationRole }>;
};

const directory = new Map<string, OrganizationRecord>();
const membershipIndex = new Map<string, Set<string>>();

export function provisionOrganization(input: {
  name: string;
  subject: string;
  email: string;
}): OrganizationRecord {
  if (!/^[A-Za-z][A-Za-z0-9 .-]{1,80}$/.test(input.name)) {
    throw new OrganizationError("ORGANIZATION_NAME_INVALID", 400);
  }
  const organization: OrganizationRecord = {
    organizationId: `org-${crypto.randomUUID()}`,
    name: input.name,
    createdBy: input.subject,
    members: { [input.subject]: { email: input.email, role: "TENANT_ADMIN" } },
  };
  directory.set(organization.organizationId, organization);
  const held = membershipIndex.get(input.subject) ?? new Set<string>();
  held.add(organization.organizationId);
  membershipIndex.set(input.subject, held);
  return organization;
}

export function authorizeGeneration(organizationId: string, subject: string, email = "unknown@invalid"): OrganizationRole {
  if (!directory.has(organizationId)) {
    const organization: OrganizationRecord = {
      organizationId,
      name: organizationId.replace(/[^A-Za-z0-9.-]/g, " ").trim() || "Organization",
      createdBy: subject,
      members: { [subject]: { email, role: "TENANT_ADMIN" } },
    };
    directory.set(organizationId, organization);
    const held = membershipIndex.get(subject) ?? new Set<string>();
    held.add(organizationId);
    membershipIndex.set(subject, held);
  }
  const organization = directory.get(organizationId);
  if (!organization) throw new OrganizationError("ORGANIZATION_NOT_FOUND", 404);
  const member = organization.members[subject];
  if (!member) throw new OrganizationError("ORGANIZATION_MEMBERSHIP_REQUIRED", 403);
  if (member.role === "VIEWER") throw new OrganizationError("ORGANIZATION_ROLE_CANNOT_GENERATE", 403);
  return member.role;
}

export function listOrganizations(subject: string): OrganizationRecord[] {
  const ids = membershipIndex.get(subject);
  if (!ids) return [];
  return [...ids].flatMap((id) => {
    const organization = directory.get(id);
    return organization ? [organization] : [];
  });
}
