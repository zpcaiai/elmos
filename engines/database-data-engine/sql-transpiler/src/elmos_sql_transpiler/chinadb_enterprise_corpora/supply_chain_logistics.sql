-- ============================================================================
-- Enterprise Supply Chain & Warehouse FIFO Allocation Workload
-- Source Dialects: Oracle PL/SQL & SQL Server T-SQL
-- ============================================================================

-- Table: Warehouses
CREATE TABLE scm_warehouses (
    warehouse_id VARCHAR2(16) NOT NULL,
    warehouse_name VARCHAR2(64) NOT NULL,
    region_code VARCHAR2(16) NOT NULL,
    capacity_cbm NUMBER(12, 2) NOT NULL,
    utilized_cbm NUMBER(12, 2) DEFAULT 0.00 NOT NULL,
    is_bonded NUMBER(1, 0) DEFAULT 0 NOT NULL,
    status VARCHAR2(16) DEFAULT 'ACTIVE' NOT NULL,
    CONSTRAINT pk_scm_wh PRIMARY KEY (warehouse_id)
);

-- Table: Inventory Lots (FIFO Tracked by expiration and manufacture date)
CREATE TABLE scm_inventory_lots (
    lot_id VARCHAR2(32) NOT NULL,
    sku_code VARCHAR2(32) NOT NULL,
    warehouse_id VARCHAR2(16) NOT NULL,
    quantity_available NUMBER(10, 0) NOT NULL,
    quantity_allocated NUMBER(10, 0) DEFAULT 0 NOT NULL,
    unit_cost NUMBER(12, 4) NOT NULL,
    manufacture_date DATE NOT NULL,
    expiry_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_scm_lots PRIMARY KEY (lot_id),
    CONSTRAINT fk_scm_lot_wh FOREIGN KEY (warehouse_id) REFERENCES scm_warehouses (warehouse_id),
    CONSTRAINT chk_scm_lot_qty CHECK (quantity_available >= 0 AND quantity_allocated >= 0)
);

-- Table: Customer Orders
CREATE TABLE scm_orders (
    order_id VARCHAR2(32) NOT NULL,
    customer_id VARCHAR2(32) NOT NULL,
    destination_region VARCHAR2(16) NOT NULL,
    order_status VARCHAR2(16) DEFAULT 'CREATED' NOT NULL,
    order_date DATE DEFAULT SYSDATE NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_scm_orders PRIMARY KEY (order_id),
    CONSTRAINT chk_scm_order_status CHECK (order_status IN ('CREATED', 'ALLOCATED', 'SHIPPED', 'DELIVERED', 'CANCELLED'))
);

-- Table: Order Items
CREATE TABLE scm_order_items (
    item_id VARCHAR2(32) NOT NULL,
    order_id VARCHAR2(32) NOT NULL,
    sku_code VARCHAR2(32) NOT NULL,
    requested_qty NUMBER(10, 0) NOT NULL,
    allocated_qty NUMBER(10, 0) DEFAULT 0 NOT NULL,
    unit_price NUMBER(12, 4) NOT NULL,
    CONSTRAINT pk_scm_items PRIMARY KEY (item_id),
    CONSTRAINT fk_scm_item_ord FOREIGN KEY (order_id) REFERENCES scm_orders (order_id)
);

-- Table: Order Lot Allocations (M:N linking order items to specific inventory lots)
CREATE TABLE scm_lot_allocations (
    allocation_id VARCHAR2(64) NOT NULL,
    item_id VARCHAR2(32) NOT NULL,
    lot_id VARCHAR2(32) NOT NULL,
    allocated_qty NUMBER(10, 0) NOT NULL,
    allocated_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_scm_alloc PRIMARY KEY (allocation_id),
    CONSTRAINT fk_scm_alloc_item FOREIGN KEY (item_id) REFERENCES scm_order_items (item_id),
    CONSTRAINT fk_scm_alloc_lot FOREIGN KEY (lot_id) REFERENCES scm_inventory_lots (lot_id)
);

-- View: SKU Inventory Stock Overview
CREATE OR REPLACE VIEW v_scm_sku_stock AS
SELECT 
    l.sku_code,
    l.warehouse_id,
    w.warehouse_name,
    SUM(l.quantity_available) AS total_available_units,
    SUM(l.quantity_allocated) AS total_allocated_units,
    ROUND(SUM(l.quantity_available * l.unit_cost), 2) AS total_available_valuation
FROM scm_inventory_lots l
JOIN scm_warehouses w ON l.warehouse_id = w.warehouse_id
GROUP BY l.sku_code, l.warehouse_id, w.warehouse_name;

-- Stored Procedure: Strict FIFO Inventory Lot Allocation
CREATE OR REPLACE PROCEDURE sp_scm_fifo_allocation (
    p_order_id IN VARCHAR2,
    p_warehouse_id IN VARCHAR2,
    p_alloc_status OUT VARCHAR2,
    p_total_items_allocated OUT NUMBER
)
IS
    CURSOR cur_items IS
        SELECT item_id, sku_code, requested_qty
        FROM scm_order_items
        WHERE order_id = p_order_id AND allocated_qty < requested_qty
        FOR UPDATE OF allocated_qty;

    CURSOR cur_lots (cp_sku VARCHAR2) IS
        SELECT lot_id, quantity_available
        FROM scm_inventory_lots
        WHERE sku_code = cp_sku 
          AND warehouse_id = p_warehouse_id 
          AND quantity_available > 0
          AND expiry_date > TRUNC(SYSDATE)
        ORDER BY expiry_date ASC, manufacture_date ASC
        FOR UPDATE OF quantity_available, quantity_allocated;

    v_item_id VARCHAR2(32);
    v_sku VARCHAR2(32);
    v_needed NUMBER(10, 0);
    v_lot_id VARCHAR2(32);
    v_lot_avail NUMBER(10, 0);
    v_allocate NUMBER(10, 0);
    v_alloc_id VARCHAR2(64);
BEGIN
    p_total_items_allocated := 0;

    OPEN cur_items;
    LOOP
        FETCH cur_items INTO v_item_id, v_sku, v_needed;
        EXIT WHEN cur_items%NOTFOUND;

        OPEN cur_lots(v_sku);
        LOOP
            FETCH cur_lots INTO v_lot_id, v_lot_avail;
            EXIT WHEN cur_lots%NOTFOUND OR v_needed = 0;

            IF v_lot_avail >= v_needed THEN
                v_allocate := v_needed;
            ELSE
                v_allocate := v_lot_avail;
            END IF;

            -- Deduct from lot available, increase allocated
            UPDATE scm_inventory_lots
            SET quantity_available = quantity_available - v_allocate,
                quantity_allocated = quantity_allocated + v_allocate,
                updated_at = SYSTIMESTAMP
            WHERE lot_id = v_lot_id;

            -- Create allocation ledger record
            v_alloc_id := 'ALC_' || v_item_id || '_' || v_lot_id;
            INSERT INTO scm_lot_allocations (
                allocation_id, item_id, lot_id, allocated_qty
            ) VALUES (
                v_alloc_id, v_item_id, v_lot_id, v_allocate
            );

            v_needed := v_needed - v_allocate;
            p_total_items_allocated := p_total_items_allocated + v_allocate;
        END LOOP;
        CLOSE cur_lots;

        -- Update order item allocated qty
        UPDATE scm_order_items
        SET allocated_qty = requested_qty - v_needed
        WHERE item_id = v_item_id;

    END LOOP;
    CLOSE cur_items;

    -- Update order status
    UPDATE scm_orders
    SET order_status = 'ALLOCATED'
    WHERE order_id = p_order_id;

    p_alloc_status := 'SUCCESS';
    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        IF cur_items%ISOPEN THEN
            CLOSE cur_items;
        END IF;
        IF cur_lots%ISOPEN THEN
            CLOSE cur_lots;
        END IF;
        ROLLBACK;
        p_alloc_status := 'ERROR_ALLOCATION_FAILED';
END sp_scm_fifo_allocation;
/
