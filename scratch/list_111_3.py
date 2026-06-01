from pathlib import Path

BASE_DIR = Path("g:/User/Downloads/TS/Code/Irrigation_Quiz")
QUESTION_DIR = BASE_DIR / "questions"

def list_111_3():
    files = sorted(QUESTION_DIR.glob("交通部111-3-*.json"))
    for f in files:
        print(f.name)

if __name__ == "__main__":
    list_111_3()
