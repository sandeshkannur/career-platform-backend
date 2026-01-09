import os
import requests

token = os.environ.get("ADMIN_TOKEN")
if not token:
    raise RuntimeError("Please set ADMIN_TOKEN in your shell first")

csv_path = "careers.csv"
url      = "http://127.0.0.1:8000/v1/admin/upload-careers"

headers = {"Authorization": f"Bearer {token}"}
files = {
    "file": (
        "careers.csv",
        open(csv_path, "rb"),
        "text/csv"
    )
}

resp = requests.post(url, headers=headers, files=files)
print("Status:", resp.status_code)
print("Response:", resp.json())
