import sys
from pathlib import Path
import re

BASE_DIR = Path("g:/User/Downloads/TS/Code/Irrigation_Quiz")
sys.path.append(str(BASE_DIR / "tools"))
import import_traffic_questions as parser

def trace():
    pdf_path = BASE_DIR / "交通部/114-2全科試題及答案.pdf"
    pages = parser.extract_all_text(pdf_path)
    subjects = parser.split_into_subjects(pages)
    
    for subj_data in subjects:
        if subj_data["subject"] == "道路交通法規":
            for section in subj_data["sections"]:
                if section["type"] == "single":
                    lines = section["lines"]
                    # Let's print all raw lines around "550"
                    found_idx = -1
                    for idx, line in enumerate(lines):
                        if "550" in line:
                            found_idx = idx
                            break
                    if found_idx != -1:
                        print("--- RAW LINES AROUND 550 ---")
                        for idx in range(max(0, found_idx - 2), min(len(lines), found_idx + 5)):
                            print(f"Line {idx}: {repr(lines[idx])}")
                        
                        # Let's run join_continued_lines on these lines and print the output
                        joined = parser.join_continued_lines(lines, "single")
                        print("\n--- JOINED LINES AROUND 550 ---")
                        for idx, jl in enumerate(joined):
                            if "550" in jl:
                                print(f"Joined {idx}: {repr(jl)}")
                                if idx + 1 < len(joined):
                                    print(f"Joined {idx+1}: {repr(joined[idx+1])}")

if __name__ == "__main__":
    trace()
