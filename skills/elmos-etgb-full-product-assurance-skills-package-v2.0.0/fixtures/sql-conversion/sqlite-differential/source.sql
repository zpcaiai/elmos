CREATE VIEW customer_totals AS
SELECT c.id AS customer_id,
       COALESCE(SUM(CASE WHEN o.status='PAID' THEN o.amount_cents ELSE 0 END), 0) AS total_cents
FROM customers c
LEFT JOIN orders o ON o.customer_id=c.id
GROUP BY c.id;

CREATE TRIGGER orders_paid_audit
AFTER UPDATE OF status ON orders
WHEN NEW.status='PAID' AND OLD.status <> 'PAID'
BEGIN
  INSERT INTO audit_log(event_type,customer_id,amount_cents)
  VALUES('PAID',NEW.customer_id,NEW.amount_cents);
END;

UPDATE orders SET status='PAID' WHERE id=2;
INSERT INTO orders(id,customer_id,amount_cents,status) VALUES(4,2,250,'PENDING');
UPDATE orders SET status='PAID' WHERE id=4;
