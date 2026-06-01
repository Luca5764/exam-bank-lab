import json
from pathlib import Path

BASE_DIR = Path("g:/User/Downloads/TS/Code/Irrigation_Quiz")
JSON_PATH = BASE_DIR / "questions/交通部111-3-汽車駕駛理論.json"
OUT_PATH = BASE_DIR / "scratch/question_36_inspect.txt"

def inspect():
    if JSON_PATH.exists():
        data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        for q in data:
            if q.get("id") == 36:
                OUT_PATH.write_text(json.dumps(q, ensure_ascii=False, indent=2), encoding="utf-8")
                print("Wrote inspect output to scratch/question_36_inspect.txt")
                return
        print("Question with ID 36 not found!")
    else:
        print(f"File {JSON_PATH} does not exist!")

if __name__ == "__main__":
    inspect()
