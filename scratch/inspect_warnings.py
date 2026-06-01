import json
from pathlib import Path

BASE_DIR = Path("g:/User/Downloads/TS/Code/Irrigation_Quiz")
QUESTION_DIR = BASE_DIR / "questions"

def inspect_warnings():
    files = sorted(QUESTION_DIR.glob("交通部*.json"))
    for f in files:
        try:
            # We need to read the internal warnings.
            # But wait, did import_traffic_questions.py remove the internal '_warnings' from the written JSON?
            # Yes, lines 855-857:
            #   q_clean = {k: v for k, v in q.items() if not k.startswith("_")}
            # So '_warnings' is NOT in the written JSON. We must parse the PDF or re-parse in memory to see the warnings!
            pass
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    # Let's import parse_pdf from tools.import_traffic_questions
    import sys
    sys.path.append(str(BASE_DIR / "tools"))
    import import_traffic_questions as parser
    
    pdf_files = sorted((BASE_DIR / "交通部").glob("*.pdf"))
    for pdf_path in pdf_files:
        try:
            results = parser.parse_pdf(pdf_path)
            for res in results:
                subj = res["subject"]
                questions = res["questions"]
                for q in questions:
                    warnings = q.get("_warnings", [])
                    if any("only" in w and "options" in w for w in warnings):
                        print(f"File: {pdf_path.name}, Subject: {subj}, ID: {q['id']}")
                        print(f"  Raw Question Text: {q['question']}")
                        print(f"  Raw Options: {q['options']}")
                        print(f"  Raw Warnings: {warnings}")
                        print("-" * 60)
        except Exception as e:
            print(f"Error parsing {pdf_path.name}: {e}")

if __name__ == "__main__":
    inspect_warnings()
