# backend/app/upload_career_keyskill_weights.py

import csv
from typing import Dict, Tuple

from app.database import SessionLocal
from app import models


CSV_PATH = "career_keyskill_weights.csv"  # File exported by export script


def load_weights_from_csv(path: str) -> Dict[Tuple[int, int], int]:
    """
    Reads CSV:
        career_id,keyskill_id,weight_percentage
    Returns dict: {(career_id, keyskill_id): weight}
    """
    mapping: Dict[Tuple[int, int], int] = {}

    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        expected = {"career_id", "keyskill_id", "weight_percentage"}
        if set(reader.fieldnames or []) != expected:
            raise ValueError(
                f"CSV columns must be {expected}, but got {reader.fieldnames}"
            )

        for row in reader:
            try:
                career_id = int(row["career_id"])
                keyskill_id = int(row["keyskill_id"])
                weight = int(row["weight_percentage"])
            except (ValueError, TypeError) as e:
                print(f"Skipping invalid row {row}: {e}")
                continue

            mapping[(career_id, keyskill_id)] = weight

    return mapping


def main():
    db = SessionLocal()

    try:
        print(f"Loading weights from CSV: {CSV_PATH}")

        weight_map = load_weights_from_csv(CSV_PATH)
        if not weight_map:
            print("No valid rows found in CSV.")
            return

        updated = 0
        missing = 0

        for (career_id, keyskill_id), weight in weight_map.items():
            stmt = (
                models.career_keyskill_association.update()
                .where(
                    models.career_keyskill_association.c.career_id == career_id,
                    models.career_keyskill_association.c.keyskill_id == keyskill_id,
                )
                .values(weight_percentage=weight)
            )

            result = db.execute(stmt)

            if result.rowcount == 0:
                print(
                    f"Warning: No association found for (career={career_id}, keyskill={keyskill_id})"
                )
                missing += 1
            else:
                updated += result.rowcount

        db.commit()
        print(f"Upload complete. Updated: {updated} rows. Missing pairs: {missing}")

    except Exception as e:
        db.rollback()
        print(f"Error updating weights. Rolled back. Error: {e}")
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()