import json
from pathlib import Path

BASE_DIR = Path("g:/User/Downloads/TS/Code/Irrigation_Quiz")
QUESTION_DIR = BASE_DIR / "questions"
OUT_PATH = BASE_DIR / "scratch/currency_inspect_utf8.txt"

def search():
    results = []
    found_count = 0
    for p in QUESTION_DIR.glob("交通部*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            for q in data:
                for key, val in q.items():
                    if isinstance(val, str) and "新臺幣" in val:
                        results.append({
                            "file": p.name,
                            "id": q.get("id"),
                            "field": key,
                            "value": val
                        })
                        found_count += 1
                        if found_count >= 15:
                            OUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
                            print("Done!")
                            return
        except Exception as e:
            print(f"Error reading {p.name}: {e}")

if __name__ == "__main__":
    search()
