import sqlite3

# Open the SQLite DB
conn = sqlite3.connect("smoke.db")
cur  = conn.cursor()

# Promote the user
cur.execute(
    "UPDATE users SET role='admin' WHERE email='admin@example.com'"
)

conn.commit()
conn.close()
print("✅ User elevated to admin")
