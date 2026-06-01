import json
from pathlib import Path

BASE_DIR = Path("g:/User/Downloads/TS/Code/Irrigation_Quiz")
QUESTION_DIR = BASE_DIR / "questions"

def search():
    found_count = 0
    for p in QUESTION_DIR.glob("交通部*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            for q in data:
                q_str = json.dumps(q, ensure_ascii=False)
                if "新臺幣" in q_str:
                    # Let's find occurrences of 新臺幣 followed by digits (with or without space)
                    # and print them
                    for key, val in q.items():
                        if isinstance(val, str) and "新臺幣" in val:
                            print(f"File: {p.name}")
                            print(f"  Field: {key}")
                            print(f"  Value: {repr(val)}")
                            found_count += 1
                            if found_count >= 10:
                                return
        except Exception as e:
            print(f"Error reading {p.name}: {e}")

if __name__ == "__main__":
    search()
