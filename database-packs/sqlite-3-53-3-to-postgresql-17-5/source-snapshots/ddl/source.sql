CREATE TABLE work_orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL,
  amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_work_orders_tenant_created
  ON work_orders (tenant_id, created_at);
