import json
import sys
import os

# Add the Backend directory to the python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal
from app.models import Job

def main():
    with SessionLocal() as db:
        jobs = db.query(Job).order_by(Job.id.desc()).limit(2).all()
        for job in jobs:
            print(f"JOB ID: {job.id}")
            print(f"STATUS: {job.status}")
            print(f"KIND: {job.kind}")
            print(f"ERROR: {job.last_error}")
            print(f"RESULT: {json.dumps(job.result_json, indent=2)}")
            print("-" * 50)

if __name__ == "__main__":
    main()
