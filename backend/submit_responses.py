# submit_responses.py
import os, requests
token = os.environ["STUDENT_TOKEN"]
answers = [
  {"question_id":"Q1","answer":"Yes"},
  {"question_id":"Q2","answer":"No"}
]
url = f"http://127.0.0.1:8000/v1/assessments/1/responses"
headers = {"Authorization": f"Bearer {token}", "Content-Type":"application/json"}
resp = requests.post(url, headers=headers, json=answers)
print(resp.json())
