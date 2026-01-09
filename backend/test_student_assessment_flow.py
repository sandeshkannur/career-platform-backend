import requests
import time

BASE_URL = "http://localhost:8000"
STUDENT_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzdHVkZW50QGV4YW1wbGUuY29tIiwiZXhwIjoxNzUyNjE4MDQyfQ.LuuPoSVuLJYvgXruZr795joNwPO2X6cJrwW_PTdyNMU"

headers = {"Authorization": f"Bearer {STUDENT_TOKEN}"}

def create_assessment():
    resp = requests.post(f"{BASE_URL}/v1/assessments/", headers=headers)
    print("\nCreate Assessment:", resp.status_code, resp.json())
    return resp.json().get("id") or resp.json().get("assessment_id")

def submit_responses(assessment_id):
    responses = [
        {"question_id": "1", "answer": "A"},
        {"question_id": "2", "answer": "B"}
    ]
    resp = requests.post(
        f"{BASE_URL}/v1/assessments/{assessment_id}/responses",
        headers=headers, json=responses
    )
    print("\nSubmit Responses:", resp.status_code, resp.json())

def submit_assessment(assessment_id):
    resp = requests.post(
        f"{BASE_URL}/v1/assessments/{assessment_id}/submit-assessment",
        headers=headers
    )
    try:
        data = resp.json()
    except Exception:
        data = resp.text
    print("\nSubmit Assessment:", resp.status_code, data)

def fetch_result(assessment_id):
    resp = requests.get(
        f"{BASE_URL}/v1/assessments/{assessment_id}/result",
        headers=headers
    )
    print("\nFetch Result:", resp.status_code, resp.json())

if __name__ == "__main__":
    aid = create_assessment()
    if aid:
        submit_responses(aid)
        submit_assessment(aid)
        print("\nWaiting for result to be ready...")
        time.sleep(2)
        fetch_result(aid)
    else:
        print("\nCould not create assessment! Check API and data.")
