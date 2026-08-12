"""db_seed.py — seed the banking SQLite DB used by banking_server.py"""
import sqlite3, os

DB = os.path.join(os.path.dirname(__file__), "banking.db")

def seed():
    if os.path.exists(DB):
        os.remove(DB)
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.executescript("""
    CREATE TABLE accounts (
        customer_id TEXT PRIMARY KEY, name TEXT, segment TEXT,
        account_type TEXT, balance REAL, city TEXT, kyc_status TEXT);
    CREATE TABLE transactions (
        txn_id INTEGER PRIMARY KEY, customer_id TEXT, txn_date TEXT,
        type TEXT, amount REAL, description TEXT);
    """)
    c.executemany("INSERT INTO accounts VALUES (?,?,?,?,?,?,?)", [
        ("C-1001","Arjun Mehta","premium","current",245000,"Mumbai","verified"),
        ("C-1002","Priya Nair","retail","savings",18500,"Chennai","verified"),
        ("C-1003","Deepak Shah","corporate","current",1200000,"Delhi","pending"),
    ])
    c.executemany("INSERT INTO transactions VALUES (?,?,?,?,?,?)", [
        (1,"C-1001","2026-06-10","credit",50000,"Salary credit"),
        (2,"C-1001","2026-06-08","debit",12000,"Utility payment"),
        (3,"C-1001","2026-06-05","debit",85000,"Wire transfer - flagged"),
        (4,"C-1002","2026-06-09","credit",8000,"Freelance payment"),
        (5,"C-1003","2026-06-07","credit",300000,"Invoice settlement"),
    ])
    conn.commit(); conn.close()
    print(f"Seeded {DB}")

if __name__ == "__main__":
    seed()
