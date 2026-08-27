CREATE TABLE accounts (
  account_id BIGINT PRIMARY KEY,
  tenant_id BIGINT NOT NULL,
  balance DECIMAL(20,4) NOT NULL CHECK (balance >= 0)
);
CREATE UNIQUE INDEX ux_accounts_tenant_account ON accounts(tenant_id, account_id);
