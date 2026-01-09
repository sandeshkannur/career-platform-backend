import os
import requests

def main():
    token = os.environ.get("ADMIN_TOKEN")
    if not token:
        raise RuntimeError("Please set ADMIN_TOKEN in your environment before running this script.")

    csv_path = "career_keyskills.csv"
    url = "http://127.0.0.1:8000/v1/admin/upload-career-keyskills"

    print(f"Uploading career-keyskill mappings from {csv_path} to {url} ...")

    headers = {"Authorization": f"Bearer {token}"}
    files = {
        "file": (
            "career_keyskills.csv",
            open(csv_path, "rb"),
            "text/csv"
        )
    }

    resp = requests.post(url, headers=headers, files=files)

    print("Status:", resp.status_code)
    try:
        print("Response JSON:", resp.json())
    except Exception:
        print("Response text:", resp.text)


if __name__ == "__main__":
    main()
