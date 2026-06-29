"""
db_tools.py
-----------
Seed a local SQLite database with sample banking/financial-services data
and expose a SAFE read-only query tool for the agent.
"""

import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).parent / "demo.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    customer_id   INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    email         TEXT,
    segment       TEXT,
    account_type  TEXT,
    balance       REAL,
    city          TEXT,
    since_year    INTEGER
);
CREATE TABLE IF NOT EXISTS orders (
    order_id      INTEGER PRIMARY KEY,
    customer_id   INTEGER REFERENCES customers(customer_id),
    product       TEXT,
    amount        REAL,
    status        TEXT,
    order_date    TEXT
);
CREATE TABLE IF NOT EXISTS transactions (
    txn_id        INTEGER PRIMARY KEY,
    customer_id   INTEGER REFERENCES customers(customer_id),
    type          TEXT,
    amount        REAL,
    description   TEXT,
    txn_date      TEXT
);
"""

CUSTOMERS = [
    (1,"Arjun Mehta","arjun@acme.in","premium","current",245000.00,"Mumbai",2018),
    (2,"Priya Nair","priya@email.com","retail","savings",18500.50,"Chennai",2020),
    (3,"Deepak Shah","deepak@corp.co","corporate","current",1200000.00,"Delhi",2015),
    (4,"Lakshmi Rao","lakshmi@me.com","retail","savings",6200.75,"Hyderabad",2022),
    (5,"Rahul Verma","rahul@tech.io","premium","loan",-85000.00,"Bengaluru",2019),
    (6,"Anita Gupta","anita@biz.com","corporate","current",870000.00,"Pune",2016),
    (7,"Kiran Kumar","kiran@mail.com","retail","savings",12300.00,"Kochi",2021),
    (8,"Sunita Sharma","sunita@net.com","retail","savings",3400.00,"Jaipur",2023),
]
ORDERS = [
    (101,1,"Mutual Fund - Bluechip",50000.00,"completed","2026-01-15"),
    (102,1,"Fixed Deposit",100000.00,"completed","2026-03-01"),
    (103,2,"RD - Monthly",2000.00,"pending","2026-05-10"),
    (104,3,"Corporate Bond",500000.00,"completed","2025-11-20"),
    (105,4,"Insurance Premium",4500.00,"completed","2026-04-01"),
    (106,5,"Home Loan EMI",22000.00,"completed","2026-06-01"),
    (107,6,"Treasury Bill",250000.00,"pending","2026-06-05"),
    (108,2,"Life Insurance",6000.00,"cancelled","2026-02-14"),
]
TRANSACTIONS = [
    (1001,1,"credit",50000.00,"Salary credit","2026-06-01"),
    (1002,1,"debit",12000.00,"Utility bill payment","2026-06-03"),
    (1003,2,"credit",8000.00,"Freelance payment","2026-06-02"),
    (1004,2,"debit",2000.00,"RD installment","2026-06-05"),
    (1005,3,"credit",300000.00,"Invoice settlement","2026-06-01"),
    (1006,5,"debit",22000.00,"Loan EMI","2026-06-01"),
    (1007,7,"credit",4500.00,"Transfer received","2026-06-04"),
    (1008,8,"debit",1200.00,"Online purchase","2026-06-03"),
]

def seed_db():
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.executescript(SCHEMA)
    cur.executemany("INSERT OR IGNORE INTO customers VALUES (?,?,?,?,?,?,?,?)", CUSTOMERS)
    cur.executemany("INSERT OR IGNORE INTO orders VALUES (?,?,?,?,?,?)", ORDERS)
    cur.executemany("INSERT OR IGNORE INTO transactions VALUES (?,?,?,?,?,?)", TRANSACTIONS)
    conn.commit()
    conn.close()

ALLOWED_TABLES  = {"customers", "orders", "transactions"}
ALLOWED_COLUMNS = {
    "customers":    {"customer_id","name","email","segment","account_type","balance","city","since_year"},
    "orders":       {"order_id","customer_id","product","amount","status","order_date"},
    "transactions": {"txn_id","customer_id","type","amount","description","txn_date"},
}

def run_db_query(table: str, filters: dict = None, limit: int = 10) -> str:
    """Safe parameterised SELECT. table and column names are whitelist-validated."""
    if table not in ALLOWED_TABLES:
        return json.dumps({"error": f"Table '{table}' not allowed. Choose: {sorted(ALLOWED_TABLES)}"})
    filters = filters or {}
    bad = set(filters.keys()) - ALLOWED_COLUMNS[table]
    if bad:
        return json.dumps({"error": f"Columns not allowed: {bad}"})
    limit = max(1, min(int(limit), 50))
    where = ("WHERE " + " AND ".join(f"{c}=?" for c in filters)) if filters else ""
    sql   = f"SELECT * FROM {table} {where} LIMIT {limit}"
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.cursor().execute(sql, list(filters.values())).fetchall()]
        conn.close()
        return json.dumps({"table": table, "rows": rows, "count": len(rows)})
    except Exception as e:
        return json.dumps({"error": str(e)})
