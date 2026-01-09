import os
import requests

token = os.environ.get("ADMIN_TOKEN")
if not token:
    raise RuntimeError("Please set ADMIN_TOKEN in your shell first")

csv_path = "keyskills.csv"
url      = "http://127.0.0.1:8000/v1/admin/upload-keyskills"

headers = {"Authorization": f"Bearer {token}"}
files = {
    "file": (
        "keyskills.csv",
        open(csv_path, "rb"),
        "text/csv"
    )
}

resp = requests.post(url, headers=headers, files=files)
print("Status:", resp.status_code)
print("Response:", resp.json())
