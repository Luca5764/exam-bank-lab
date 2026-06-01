import sys
from pathlib import Path

BASE_DIR = Path("g:/User/Downloads/TS/Code/Irrigation_Quiz")
sys.path.append(str(BASE_DIR / "tools"))
import import_traffic_questions as parser

def inspect():
    # Let's inspect the files that had warnings
    targets = [
        "114-2全科試題及答案.pdf",
        "114-3全科試題及答案.pdf",
        "114全科試題及答案.pdf",
        "115-1全科試題及答案.pdf"
    ]
    
    for filename in targets:
        pdf_path = BASE_DIR / "交通部" / filename
        if pdf_path.exists():
            results = parser.parse_pdf(pdf_path)
            for res in results:
                subj = res["subject"]
                questions = res["questions"]
                for q in questions:
                    warnings = q.get("_warnings", [])
                    if any("only" in w for w in warnings):
                        print(f"File: {filename}, Subject: {subj}, ID: {q['id']}")
                        print(f"  Question: {repr(q['question'])}")
                        print(f"  Options: {q['options']}")
                        print(f"  Warnings: {warnings}")
                        print("-" * 60)

if __name__ == "__main__":
    inspect()
