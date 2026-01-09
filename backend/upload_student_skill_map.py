import os
import csv
import requests

def main():
    token = os.environ.get("ADMIN_TOKEN")
    if not token:
        raise RuntimeError("Please set ADMIN_TOKEN in your environment first")

    csv_path = "student_skill_map.csv"
    url = "http://127.0.0.1:8000/v1/admin/student-skill-map"

    print(f"Uploading student-skill mappings from {csv_path} ...")

    # Read CSV
    mappings = []
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mappings.append({
                "student_id": int(row["student_id"]),
                "skill_id": int(row["skill_id"]),
            })

    headers = {"Authorization": f"Bearer {token}"}

    resp = requests.post(url, json=mappings, headers=headers)
    print("Status:", resp.status_code)
    try:
        print("Response JSON:", resp.json())
    except Exception:
        print("Response text:", resp.text)


if __name__ == "__main__":
    main()
