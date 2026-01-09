# Step 1: Starting assessment engine logic
# This script sends a request to create an assessment using the provided token.
import os
import requests

token = os.environ.get("STUDENT_TOKEN") or os.environ.get("ADMIN_TOKEN")

if not token:
    if os.environ.get("CI") == "true":
        print("[CI MODE] Skipping token check — no token provided.")
    else:
        raise RuntimeError("Please set STUDENT_TOKEN (or ADMIN_TOKEN) in your shell first")
else:
    url = "http://127.0.0.1:8000/v1/assessments"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        resp = requests.post(url, headers=headers)
        print("Status:", resp.status_code)
        print("Response:", resp.json())
    except Exception as e:
        print("❌ Request failed:", e)
        raise RuntimeError("Failed to create assessment. Check the server status or your token.")
