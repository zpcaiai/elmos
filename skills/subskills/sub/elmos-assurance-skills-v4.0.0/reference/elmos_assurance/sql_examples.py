"""Executable SQLite counterexamples only; NOT a cross-database certification."""
from __future__ import annotations
import sqlite3
from typing import Iterable

def not_in_vs_not_exists(outer: Iterable[int | None], inner: Iterable[int | None]) -> tuple[list[tuple], list[tuple]]:
    with sqlite3.connect(":memory:") as db:
        db.executescript("CREATE TABLE outer_t(x INTEGER); CREATE TABLE inner_t(y INTEGER);")
        db.executemany("INSERT INTO outer_t VALUES (?)", [(x,) for x in outer])
        db.executemany("INSERT INTO inner_t VALUES (?)", [(y,) for y in inner])
        a = db.execute("SELECT x FROM outer_t WHERE x NOT IN (SELECT y FROM inner_t) ORDER BY rowid").fetchall()
        b = db.execute("SELECT x FROM outer_t WHERE NOT EXISTS (SELECT 1 FROM inner_t WHERE inner_t.y = outer_t.x) ORDER BY rowid").fetchall()
        return a, b
