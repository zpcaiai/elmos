PRAGMA foreign_keys=ON;
CREATE TABLE customers(
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL
);
CREATE TABLE orders(
  id INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  amount_cents INTEGER NOT NULL CHECK(amount_cents >= 0),
  status TEXT NOT NULL CHECK(status IN ('PENDING','PAID','CANCELLED'))
);
CREATE TABLE audit_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL,
  customer_id INTEGER NOT NULL,
  amount_cents INTEGER NOT NULL
);
INSERT INTO customers(id,name) VALUES (1,'Alice'),(2,'Bob');
INSERT INTO orders(id,customer_id,amount_cents,status) VALUES
  (1,1,1200,'PAID'),
  (2,1,800,'PENDING'),
  (3,2,500,'PAID');
