import json
from pathlib import Path

BASE_DIR = Path("g:/User/Downloads/TS/Code/Irrigation_Quiz")
JSON_PATH = BASE_DIR / "questions/交通部111-3-汽車駕駛理論.json"
OUT_PATH = BASE_DIR / "scratch/111_3_q36_inspect_utf8.txt"

def inspect():
    if JSON_PATH.exists():
        data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        for q in data:
            if q.get("id") == 36:
                OUT_PATH.write_text(json.dumps(q, ensure_ascii=False, indent=2), encoding="utf-8")
                print("Done!")
                return
        print("Question ID 36 not found!")
    else:
        print("JSON file not found!")

if __name__ == "__main__":
    inspect()
