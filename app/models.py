import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'instance', 'students.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            domain TEXT,
            joining_date TEXT,
            category TEXT,
            ieee_id TEXT,
            qr_code TEXT
        )
    """)
    conn.commit()
    conn.close()

def clear_and_insert_students(data):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Clear old data
    c.execute("DELETE FROM students")

    # Insert new data
    for row in data:
        c.execute("""
            INSERT INTO students (name, domain, joining_date, category, ieee_id, qr_code)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (row["Name"], row["Domain"], row["Joining Date"], row["Category"], row["IEEE ID"], row["QR"]))
    conn.commit()
    conn.close()

init_db()
