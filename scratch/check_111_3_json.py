import json
from pathlib import Path

BASE_DIR = Path("g:/User/Downloads/TS/Code/Irrigation_Quiz")
JSON_PATH = BASE_DIR / "questions/交通部111-3-汽車駕駛理論.json"
OUT_PATH = BASE_DIR / "scratch/check_111_3_json.txt"

def check():
    if JSON_PATH.exists():
        data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        print(f"Total questions in 111-3-駕駛理論: {len(data)}")
        
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            for q in data:
                f.write(f"ID {q['id']}: {q['question']}\n")
                f.write(f"  Options: {q.get('options')}\n")
                f.write(f"  Answer: {q.get('answer')}\n")
                if "noShuffle" in q:
                    f.write(f"  noShuffle: {q['noShuffle']}\n")
                f.write("\n")
        print("Done! Output written to scratch/check_111_3_json.txt")
    else:
        print("JSON file not found!")

if __name__ == "__main__":
    check()
