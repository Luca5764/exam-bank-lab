import json
from pathlib import Path

BASE_DIR = Path("g:/User/Downloads/TS/Code/Irrigation_Quiz")
JSON_PATH = BASE_DIR / "questions/交通部113-3-汽車駕駛理論.json"
OUT_PATH = BASE_DIR / "scratch/113_3_inspect_utf8.txt"

def inspect():
    if JSON_PATH.exists():
        data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        results = []
        for q in data:
            if q.get("id") in (20, 21):
                results.append(q)
        OUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Done!")
    else:
        print("JSON file not found!")

if __name__ == "__main__":
    inspect()
