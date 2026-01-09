import os
import requests

def main():
    token = os.environ.get("ADMIN_TOKEN")
    if not token:
        raise RuntimeError("Please set ADMIN_TOKEN in your environment first")

    url = "http://127.0.0.1:8000/v1/students/students"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    students = [
        {"name": "Student One", "grade": 9},
        {"name": "Student Two", "grade": 10},
        {"name": "Student Three", "grade": 8},
    ]

    for s in students:
        print(f"Creating student: {s}")
        resp = requests.post(url, json=s, headers=headers)
        print("Status:", resp.status_code)
        try:
            print("Response JSON:", resp.json())
        except Exception:
            print("Response text:", resp.text)
        print("-" * 40)


if __name__ == "__main__":
    main()
