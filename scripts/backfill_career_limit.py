"""
Backfill script — truncate recommended_careers to first 9 elements
for historical assessment_results rows that have 368 careers stored.
Run once on EC2 after deployment. Safe and idempotent.
"""
import sys
sys.path.insert(0, '/app')

from app.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    result = db.execute(text("""
        UPDATE assessment_results
        SET recommended_careers = (
            SELECT jsonb_agg(elem)
            FROM (
                SELECT elem
                FROM jsonb_array_elements(recommended_careers) WITH ORDINALITY AS t(elem, ord)
                ORDER BY ord
                LIMIT 9
            ) sub
        )
        WHERE jsonb_array_length(recommended_careers) > 9
    """))
    db.commit()
    print(f"Backfill complete. Rows updated: {result.rowcount}")
except Exception as e:
    db.rollback()
    print(f"Error: {e}")
finally:
    db.close()
