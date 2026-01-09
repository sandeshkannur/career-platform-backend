import sqlite3

conn = sqlite3.connect("alembic_draft.db")
tables = [row[0] for row in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table';"
)]
conn.close()

print("Tables in alembic_draft.db:")
for t in tables:
    print(" -", t)
