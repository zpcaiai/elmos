module TenantIsolation
sig Tenant {}
sig Account { tenant: one Tenant }
sig Artifact { tenant: one Tenant, owner: one Account }
sig Request { account: one Account, target: one Artifact }

pred Allowed[r: Request] {
  r.account.tenant = r.target.tenant
}

assert NoCrossTenantRead {
  all r: Request | Allowed[r] implies r.account.tenant = r.target.tenant
}
check NoCrossTenantRead for 6
