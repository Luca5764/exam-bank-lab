import os
from pathlib import Path
from datetime import datetime

BASE_DIR = Path("g:/User/Downloads/TS/Code/Irrigation_Quiz")
QUESTION_DIR = BASE_DIR / "questions"

def check_mtime():
    files = sorted(QUESTION_DIR.glob("交通部*.json"))
    if not files:
        print("No files found!")
        return
    for f in files:
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        print(f"{f.name}: {mtime}")

if __name__ == "__main__":
    check_mtime()
