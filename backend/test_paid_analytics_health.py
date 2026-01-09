import os
import requests

def main():
    token = os.environ.get("ADMIN_TOKEN")
    if not token:
        raise RuntimeError("Please set ADMIN_TOKEN in your environment first")

    # This URL matches what Swagger shows in your screenshot
    url = "http://127.0.0.1:8000/v1/analytics/analytics/analytics/health"

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
