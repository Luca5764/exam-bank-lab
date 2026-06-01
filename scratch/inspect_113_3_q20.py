import pymupdf
from pathlib import Path

BASE_DIR = Path("g:/User/Downloads/TS/Code/Irrigation_Quiz")
PDF_PATH = BASE_DIR / "交通部/113-3全科試題及答案.pdf"

def inspect():
    doc = pymupdf.open(str(PDF_PATH))
    # Search all pages for "陡坡前" or "陡坡" or check driving theory pages
    for page_idx, page in enumerate(doc):
        text = page.get_text("text") or ""
        if "最小迴轉半徑" in text or "迴轉半徑愈" in text:
            print(f"Found on Page {page_idx + 1}:")
            print("--- RAW TEXT ---")
            print(text)
            print("----------------\n")
    doc.close()

if __name__ == "__main__":
    inspect()
