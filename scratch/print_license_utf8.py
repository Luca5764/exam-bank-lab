import json
from pathlib import Path

BASE_DIR = Path("g:/User/Downloads/TS/Code/Irrigation_Quiz")
QUESTION_DIR = BASE_DIR / "questions"
OUT_PATH = BASE_DIR / "scratch/license_inspect_utf8.txt"

def inspect():
    results = []
    for p in QUESTION_DIR.glob("交通部*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            for q in data:
                if "從事休閒遊憩露營" in q.get("question", ""):
                    results.append({
                        "file": p.name,
                        "question": q
                    })
        except Exception as e:
            print(f"Error reading {p.name}: {e}")
            
    OUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Done!")

if __name__ == "__main__":
    inspect()
