import sys
from pathlib import Path
import json

BASE_DIR = Path("g:/User/Downloads/TS/Code/Irrigation_Quiz")
sys.path.append(str(BASE_DIR / "tools"))
import import_traffic_questions as parser

def inspect():
    targets = [
        "114-2全科試題及答案.pdf",
        "114-3全科試題及答案.pdf",
        "114全科試題及答案.pdf",
        "115-1全科試題及答案.pdf"
    ]
    
    results_list = []
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
                        results_list.append({
                            "file": filename,
                            "subject": subj,
                            "id": q["id"],
                            "question": q["question"],
                            "options": q["options"]
                        })
                        
    (BASE_DIR / "scratch/anchored_warnings_utf8.txt").write_text(
        json.dumps(results_list, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("Done!")

if __name__ == "__main__":
    inspect()
