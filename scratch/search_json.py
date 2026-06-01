import json
from pathlib import Path

BASE_DIR = Path("g:/User/Downloads/TS/Code/Irrigation_Quiz")
QUESTION_DIR = BASE_DIR / "questions"

def search():
    found = False
    for p in QUESTION_DIR.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            for q in data:
                if "行駛之汽車與汽車" in q.get("question", "") or "衝撞力之大小與何者有關" in q.get("question", ""):
                    print(f"Found in {p.name}:")
                    print(json.dumps(q, ensure_ascii=False, indent=2))
                    found = True
        except Exception as e:
            print(f"Error reading {p.name}: {e}")
    if not found:
        print("Question NOT found in any JSON file!")

if __name__ == "__main__":
    search()
