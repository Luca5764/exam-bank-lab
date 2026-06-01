import json
from pathlib import Path

BASE_DIR = Path("g:/User/Downloads/TS/Code/Irrigation_Quiz")
JSON_PATH = BASE_DIR / "questions/交通部113-3-汽車駕駛理論.json"

def inspect():
    if JSON_PATH.exists():
        data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        # The single choice section has 40 questions, so Q20 of MC corresponds to ID 20.
        # Wait, the PDF shows Q20 is a single choice question:
        #   "20.  汽車軸距愈長，輪距愈寬，在轉彎時（1）最小迴轉半徑愈小 （2）最小迴轉半徑愈大（3）內外輪差愈小（4）內外輪差不變。"
        # Yes, ID 20 is single-choice!
        for q in data:
            if q.get("id") in (20, 21):
                print(f"ID {q['id']}:")
                print(json.dumps(q, ensure_ascii=False, indent=2))
                print("-" * 50)
    else:
        print("JSON file not found!")

if __name__ == "__main__":
    inspect()
