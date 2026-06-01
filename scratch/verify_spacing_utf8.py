import json
from pathlib import Path

BASE_DIR = Path("g:/User/Downloads/TS/Code/Irrigation_Quiz")
QUESTION_DIR = BASE_DIR / "questions"
OUT_PATH = BASE_DIR / "scratch/spacing_inspect_utf8.txt"

def inspect():
    results = []
    
    # 1. Look for 甲類大客車之軸距為
    for p in QUESTION_DIR.glob("交通部*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            for q in data:
                if "甲類大客車之軸距為" in q.get("question", ""):
                    results.append({
                        "file": p.name,
                        "type": "bus",
                        "question": q
                    })
                if "新臺幣" in json.dumps(q, ensure_ascii=False) and len(results) < 5:
                    results.append({
                        "file": p.name,
                        "type": "currency",
                        "question": q
                    })
        except Exception as e:
            print(f"Error reading {p.name}: {e}")
            
    OUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Done!")

if __name__ == "__main__":
    inspect()
