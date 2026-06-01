import pymupdf
from pathlib import Path

BASE_DIR = Path("g:/User/Downloads/TS/Code/Irrigation_Quiz")
PDF_PATH = BASE_DIR / "交通部/114-2全科試題及答案.pdf"
OUT_PATH = BASE_DIR / "scratch/114_2_raw_utf8.txt"

def extract():
    doc = pymupdf.open(str(PDF_PATH))
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for page_idx, page in enumerate(doc):
            text = page.get_text("text") or ""
            if "汽缸總排氣量" in text or "550" in text:
                f.write(f"=== Page {page_idx + 1} ===\n")
                f.write(text)
                f.write("\n\n")
    doc.close()
    print("Done!")

if __name__ == "__main__":
    extract()
