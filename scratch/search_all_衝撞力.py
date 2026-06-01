import json
from pathlib import Path

BASE_DIR = Path("g:/User/Downloads/TS/Code/Irrigation_Quiz")
QUESTION_DIR = BASE_DIR / "questions"

def search():
    files = sorted(QUESTION_DIR.glob("交通部*.json"))
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            for q in data:
                q_str = json.dumps(q, ensure_ascii=False)
                if "衝撞力" in q_str:
                    print(f"File: {f.name}, ID: {q['id']}")
                    print(json.dumps(q, ensure_ascii=False, indent=2))
                    print("-" * 50)
        except Exception as e:
            print(f"Error reading {f.name}: {e}")

if __name__ == "__main__":
    search()
