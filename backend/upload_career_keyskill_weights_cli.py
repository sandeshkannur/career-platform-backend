import os
import requests

# 1) Grab your admin token from the environment
token = os.environ.get("ADMIN_TOKEN")
if not token:
    raise RuntimeError("Please set ADMIN_TOKEN in your shell first")

# 2) CSV file and endpoint
csv_path = "career_keyskill_weights.csv"  # adjust if your file is elsewhere
url      = "http://127.0.0.1:8000/v1/admin/upload-career-keyskill-weights"

# 3) Build headers and files payload
headers = {
    "Authorization": f"Bearer {token}",
    "accept": "application/json",
}
files = {
    "file": (
        "career_keyskill_weights.csv",
        open(csv_path, "rb"),
        "text/csv",
    )
}

# 4) Fire the request
print(f"Uploading {csv_path} to {url} ...")
resp = requests.post(url, headers=headers, files=files)

print("Status code:", resp.status_code)
try:
    print("Response JSON:", resp.json())
except Exception:
    print("Raw response:", resp.text)
