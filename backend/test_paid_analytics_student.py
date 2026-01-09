import os
import requests

def main():
    token = os.environ.get("ADMIN_TOKEN")
    if not token:
        raise RuntimeError("Please set ADMIN_TOKEN in your environment first")

    # 👉 Replace this with the exact Request URL pattern from Swagger
    student_id = 1
    url = f"http://127.0.0.1:8000/v1/paid-analytics/{student_id}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    print(f"Calling {url} ...")
    resp = requests.get(url, headers=headers)

    print("Status:", resp.status_code)
    try:
        print("Response JSON:", resp.json())
    except Exception:
        print("Response text:", resp.text)


if __name__ == "__main__":
    main()
