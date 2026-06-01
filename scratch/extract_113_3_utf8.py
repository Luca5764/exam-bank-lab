import pymupdf
from pathlib import Path

BASE_DIR = Path("g:/User/Downloads/TS/Code/Irrigation_Quiz")
PDF_PATH = BASE_DIR / "交通部/113-3全科試題及答案.pdf"
OUT_PATH = BASE_DIR / "scratch/113_3_page_15_utf8.txt"

def extract():
    doc = pymupdf.open(str(PDF_PATH))
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(doc[14].get_text("text") or "")
    doc.close()
    print("Done!")

if __name__ == "__main__":
    extract()
