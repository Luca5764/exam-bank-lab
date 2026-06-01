import pymupdf
from pathlib import Path

BASE_DIR = Path("g:/User/Downloads/TS/Code/Irrigation_Quiz")
SOURCE_DIR = BASE_DIR / "交通部"

def search():
    pdf_files = sorted(SOURCE_DIR.glob("*.pdf"))
    for pdf_path in pdf_files:
        doc = pymupdf.open(str(pdf_path))
        for page_idx, page in enumerate(doc):
            text = page.get_text("text") or ""
            if "甲類大客車" in text:
                print(f"Found in {pdf_path.name} on Page {page_idx + 1}:")
                print("--- RAW TEXT ---")
                print(text)
                print("----------------\n")
        doc.close()

if __name__ == "__main__":
    search()
