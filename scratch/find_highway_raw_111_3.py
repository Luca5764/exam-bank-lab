import pymupdf
from pathlib import Path

BASE_DIR = Path("g:/User/Downloads/TS/Code/Irrigation_Quiz")
PDF_PATH = BASE_DIR / "交通部/111-3全科試題及答案.pdf"
OUT_PATH = BASE_DIR / "scratch/highway_raw_111_3.txt"

def search():
    doc = pymupdf.open(str(PDF_PATH))
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for page_idx, page in enumerate(doc):
            text = page.get_text("text") or ""
            if "路肩上停車待援" in text:
                f.write(f"=== Page {page_idx + 1} ===\n")
                f.write(text)
                f.write("\n\n")
    doc.close()
    print("Done!")

if __name__ == "__main__":
    search()
