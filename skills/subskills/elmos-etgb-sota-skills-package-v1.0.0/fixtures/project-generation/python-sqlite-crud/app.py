from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Product:
    id: int
    sku: str
    stock: int


class InventoryService:
    def __init__(self, database: str | Path = ":memory:") -> None:
        self.conn = sqlite3.connect(str(database), isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS products(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          sku TEXT NOT NULL UNIQUE,
          stock INTEGER NOT NULL CHECK(stock >= 0)
        );
        CREATE TABLE IF NOT EXISTS idempotency(
          key TEXT PRIMARY KEY,
          product_id INTEGER NOT NULL REFERENCES products(id)
        );
        CREATE TABLE IF NOT EXISTS audit(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          product_id INTEGER NOT NULL,
          event TEXT NOT NULL,
          delta INTEGER NOT NULL
        );
        """)

    def create_product(self, sku: str, stock: int, idempotency_key: str) -> Product:
        if not sku or stock < 0 or not idempotency_key:
            raise ValueError("INVALID_INPUT")
        existing = self.conn.execute(
            "SELECT p.* FROM idempotency i JOIN products p ON p.id=i.product_id WHERE i.key=?",
            (idempotency_key,),
        ).fetchone()
        if existing:
            return Product(existing["id"], existing["sku"], existing["stock"])
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            cur = self.conn.execute("INSERT INTO products(sku,stock) VALUES(?,?)", (sku, stock))
            product_id = int(cur.lastrowid)
            self.conn.execute("INSERT INTO idempotency(key,product_id) VALUES(?,?)", (idempotency_key, product_id))
            self.conn.execute("INSERT INTO audit(product_id,event,delta) VALUES(?,?,?)", (product_id, "CREATE", stock))
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        return self.get_product(product_id)

    def get_product(self, product_id: int) -> Product:
        row = self.conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not row:
            raise KeyError("NOT_FOUND")
        return Product(row["id"], row["sku"], row["stock"])

    def purchase(self, product_id: int, quantity: int) -> Product:
        if quantity <= 0:
            raise ValueError("INVALID_QUANTITY")
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            row = self.conn.execute("SELECT stock FROM products WHERE id=?", (product_id,)).fetchone()
            if row is None:
                raise KeyError("NOT_FOUND")
            if row["stock"] < quantity:
                raise RuntimeError("INSUFFICIENT_STOCK")
            self.conn.execute("UPDATE products SET stock=stock-? WHERE id=?", (quantity, product_id))
            self.conn.execute("INSERT INTO audit(product_id,event,delta) VALUES(?,?,?)", (product_id, "PURCHASE", -quantity))
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        return self.get_product(product_id)

    def audit_events(self, product_id: int) -> list[tuple[str, int]]:
        return [(r["event"], r["delta"]) for r in self.conn.execute("SELECT event,delta FROM audit WHERE product_id=? ORDER BY id", (product_id,))]
