import pymupdf
from pathlib import Path

BASE_DIR = Path("g:/User/Downloads/TS/Code/Irrigation_Quiz")
PDF_PATH = BASE_DIR / "交通部/111年汽車檢、考驗員檢定各學科筆試試題及答案-0502修正.pdf"
OUT_PATH = BASE_DIR / "scratch/bus_raw_utf8.txt"

def extract():
    doc = pymupdf.open(str(PDF_PATH))
    # Page 8 is 0-indexed index 7
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(doc[7].get_text("text") or "")
    doc.close()
    print("Done!")

if __name__ == "__main__":
    extract()
