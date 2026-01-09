import subprocess

scripts = [
    "upload_clusters.py",
    "upload_careers.py",
    "upload_keyskills.py",
    "create_assessment.py",
    "submit_responses.py",
    "fetch_result.py"
]

print("\n Running Full Automated Test Pipeline...\n")

for script in scripts:
    print(f"\n Executing: {script}")
    try:
        result = subprocess.run(
            ["python", script],
            check=True,
            capture_output=True,
            text=True
        )
        print(f" {script} ran successfully.\n--- STDOUT ---\n{result.stdout}\n--- STDERR ---\n{result.stderr}")
    except subprocess.CalledProcessError as e:
        print(f" Error running {script}:\n--- STDOUT ---\n{e.stdout}\n--- STDERR ---\n{e.stderr}")
        break  # stop on first error

print("\n All available test scripts executed.\n")
