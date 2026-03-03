# app/wait_for_db.py

import os
import time
import psycopg2
from psycopg2 import OperationalError

def wait_for_postgres(host, port, user, password, db, timeout=30):
    # If we’re running tests and want to skip the Docker wait, bail out immediately
    if os.getenv("SKIP_DB_WAIT") == "1":
        print("⚠️  Skipping Postgres wait (SKIP_DB_WAIT=1)")
        return

    start = time.time()
    while True:
        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                dbname=db,
            )
            conn.close()
            print("✅ PostgreSQL is ready!")
            break
        except OperationalError as e:
            if time.time() - start > timeout:
                raise TimeoutError("❌ Could not connect to PostgreSQL within timeout") from e
            print("⏳ Waiting for PostgreSQL to be ready...")
            time.sleep(1)
