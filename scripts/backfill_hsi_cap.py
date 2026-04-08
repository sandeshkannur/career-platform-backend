"""
Backfill script — cap existing hsi_score > 100 to 100.0
Run once on EC2 after Fix 1 is deployed.
Safe: only updates rows where hsi_score > 100
"""
import os, sys
sys.path.insert(0, '/app')

from app.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    result = db.execute(text(
        "UPDATE student_skill_scores SET hsi_score = 100.0 WHERE hsi_score > 100.0"
    ))
    db.commit()
    print(f"Backfill complete. Rows updated: {result.rowcount}")
except Exception as e:
    db.rollback()
    print(f"Error: {e}")
finally:
    db.close()
