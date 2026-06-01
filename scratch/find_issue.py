import os
from pathlib import Path
import pymupdf

BASE_DIR = Path("g:/User/Downloads/TS/Code/Irrigation_Quiz")
SOURCE_DIR = BASE_DIR / "交通部"
OUT_FILE = BASE_DIR / "scratch/find_issue_out.txt"

def find_text():
    pdf_files = sorted(SOURCE_DIR.glob("*.pdf"))
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        for pdf_path in pdf_files:
            doc = pymupdf.open(str(pdf_path))
            for page_idx, page in enumerate(doc):
                text = page.get_text("text") or ""
                if "衝撞力" in text:
                    f.write(f"Found in {pdf_path.name} on Page {page_idx + 1}:\n")
                    f.write("--- RAW TEXT ---\n")
                    f.write(text)
                    f.write("\n----------------\n\n")
            doc.close()
    print("Done! Output written to scratch/find_issue_out.txt")

if __name__ == "__main__":
    find_text()
