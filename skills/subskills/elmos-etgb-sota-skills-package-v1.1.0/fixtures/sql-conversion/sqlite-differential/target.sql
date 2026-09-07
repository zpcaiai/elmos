CREATE VIEW customer_totals AS
SELECT c.id AS customer_id,
       (SELECT COALESCE(SUM(o.amount_cents),0)
          FROM orders o
         WHERE o.customer_id=c.id AND o.status='PAID') AS total_cents
FROM customers c;

CREATE TRIGGER orders_paid_audit
AFTER UPDATE OF status ON orders
FOR EACH ROW
WHEN (NEW.status = 'PAID') AND (OLD.status != 'PAID')
BEGIN
  INSERT INTO audit_log(event_type,customer_id,amount_cents)
  SELECT 'PAID', NEW.customer_id, NEW.amount_cents;
END;

UPDATE orders SET status='PAID' WHERE id IN (SELECT id FROM orders WHERE id=2);
INSERT INTO orders(customer_id,id,status,amount_cents) VALUES(2,4,'PENDING',250);
UPDATE orders SET status='PAID' WHERE id=4 AND status='PENDING';
