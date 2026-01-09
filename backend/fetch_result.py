import os
import requests

# 1) Grab the same token
token = os.environ.get("STUDENT_TOKEN") or os.environ.get("ADMIN_TOKEN")
if not token:
    raise RuntimeError("Please set STUDENT_TOKEN (or ADMIN_TOKEN) in your shell first")

# 2) Point to your assessment ID
assessment_id = 1   # or whatever ID was returned by create_assessment.py

url = f"http://127.0.0.1:8000/v1/assessments/{assessment_id}/result"
headers = {"Authorization": f"Bearer {token}"}

# 3) Fetch result
resp = requests.get(url, headers=headers)
print("Status:", resp.status_code)
print("Response:", resp.json())
