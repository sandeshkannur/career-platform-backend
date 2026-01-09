import os
import sys
import requests

# This script uploads CLUSTERS from career_clusters.csv
# to the /v1/admin/upload-career-clusters endpoint.

def main():
    # 1) Grab your admin token from the environment
    token = os.environ.get("ADMIN_TOKEN")
    if not token:
        print("ERROR: Please set ADMIN_TOKEN in your environment before running this script.")
        sys.exit(1)

    # 2) CSV file and endpoint  ✅ NOTE: changed here
    csv_path = "career_clusters.csv"
    url = "http://127.0.0.1:8000/v1/admin/upload-career-clusters"

    if not os.path.exists(csv_path):
        print(f"ERROR: CSV file not found: {csv_path}")
        sys.exit(1)

    # 3) Build headers and files payload
    headers = {"Authorization": f"Bearer {token}"}
    files = {
        "file": (
            os.path.basename(csv_path),
            open(csv_path, "rb"),
            "text/csv",
        )
    }

    # 4) Fire the request
    print(f"Uploading clusters from {csv_path} to {url} ...")
    try:
        resp = requests.post(url, headers=headers, files=files, timeout=60)
    except Exception as e:
        print("ERROR: Request failed:", e)
        sys.exit(1)

    # 5) Print out what we got
    print("Status:", resp.status_code)
    try:
        print("Response JSON:", resp.json())
    except Exception:
        print("Raw Response Text:", resp.text)

    if not resp.ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
