import re
import pymupdf
from pathlib import Path

BASE_DIR = Path("g:/User/Downloads/TS/Code/Irrigation_Quiz")
SOURCE_DIR = BASE_DIR / "交通部"

def search():
    pattern = re.compile(r"[\u4e00-\u9fff]\s+[0-9]")
    pdf_files = sorted(SOURCE_DIR.glob("*.pdf"))
    count = 0
    for pdf_path in pdf_files:
        doc = pymupdf.open(str(pdf_path))
        for page_idx, page in enumerate(doc):
            text = page.get_text("text") or ""
            matches = list(pattern.finditer(text))
            for m in matches[:5]: # Print first 5 matches per page to avoid clutter
                start = max(0, m.start() - 10)
                end = min(len(text), m.end() + 10)
                snippet = text[start:end].replace("\n", " ")
                print(f"File: {pdf_path.name}, Page: {page_idx + 1}, Match: {repr(m.group())}, Snippet: {repr(snippet)}")
                count += 1
        doc.close()
    print(f"Total matches found in all PDFs: {count}")

if __name__ == "__main__":
    search()
