import pymupdf
from pathlib import Path

BASE_DIR = Path("g:/User/Downloads/TS/Code/Irrigation_Quiz")
PDF_PATH = BASE_DIR / "交通部/111-3全科試題及答案.pdf"
OUT_PATH = BASE_DIR / "scratch/111_3_pages.txt"

def extract():
    doc = pymupdf.open(str(PDF_PATH))
    print(f"Total pages: {len(doc)}")
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for p_idx in [14, 15, 16]:  # Pages 15, 16, 17 (0-indexed 14, 15, 16)
            if p_idx < len(doc):
                f.write(f"=== PAGE {p_idx + 1} ===\n")
                f.write(doc[p_idx].get_text("text") or "")
                f.write("\n\n")
    doc.close()
    print("Done! Extracted pages 15, 16, 17 to scratch/111_3_pages.txt")

if __name__ == "__main__":
    extract()
