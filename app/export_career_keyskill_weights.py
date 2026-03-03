# backend/app/export_career_keyskill_weights.py

import csv
from collections import defaultdict

from app.database import SessionLocal
from app import models


def main():
    db = SessionLocal()

    try:
        print("Reading career_keyskill_association table...")

        # ⚠️ Select ONLY EXISTING columns (career_id, keyskill_id)
        rows = db.execute(
            models.career_keyskill_association.select()
        ).fetchall()

        if not rows:
            print("No rows found in career_keyskill_association.")
            return

        # Group keyskills by career to compute equal weights
        career_to_keyskills = defaultdict(list)
        for row in rows:
            # Each row object has attributes matching column names
            career_id = row.career_id
            keyskill_id = row.keyskill_id
            career_to_keyskills[career_id].append(keyskill_id)

        # Assign equal-split weights (100% divided across all keyskills per career)
        output_rows = []

        for career_id, keyskill_ids in career_to_keyskills.items():
            n = len(keyskill_ids)
            if n == 0:
                continue

            base_weight = 100 // n
            remainder = 100 - (base_weight * n)

            # Add +1 to first <remainder> entries to total exactly 100
            for index, ks_id in enumerate(keyskill_ids):
                weight = base_weight + (1 if index < remainder else 0)

                output_rows.append({
                    "career_id": career_id,
                    "keyskill_id": ks_id,
                    "weight_percentage": weight,
                })

        # Write CSV
        output_path = "career_keyskill_weights.csv"

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["career_id", "keyskill_id", "weight_percentage"]
            )
            writer.writeheader()
            writer.writerows(output_rows)

        print(f"Export complete. Wrote {len(output_rows)} rows to {output_path}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
