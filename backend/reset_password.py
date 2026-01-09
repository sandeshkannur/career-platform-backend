import psycopg2

# 1) Connect using whatever credentials currently work.
#    If 'testpass123' is wrong, change it here to the current password 
#    so you can connect and then reset it.
conn = psycopg2.connect(
    host="127.0.0.1",
    port=5433,
    user="counseling",
    password="testpass123",  # current password
    dbname="counseling_db",
)
cur = conn.cursor()

# 2) Reset the password to the one in your .env
cur.execute("ALTER USER counseling WITH PASSWORD 'testpass123';")

conn.commit()
cur.close()
conn.close()

print("✅ counseling user password reset to 'testpass123'")
