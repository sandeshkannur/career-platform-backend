# reset_admin.py
import sqlite3

# point at the same SQLite file your app is using in dev
conn = sqlite3.connect("dev.sqlite")
conn.execute(
    "UPDATE users SET role='admin' WHERE email='admin@example.com';"
)
conn.commit()
conn.close()

print("✅ Elevated admin@example.com to admin")
