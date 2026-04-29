import pdfplumber
import sys

pdf_path = r'G:\User\Downloads\TS\Code\Irrigation_Quiz\農田水利\105\105_不分職等-共同科目-公文與農田水利相關法規.pdf'
pdf = pdfplumber.open(pdf_path)

p = pdf.pages[0]
orient = "landscape" if p.width > p.height else "portrait"

with open("test_pdf_output.txt", "w", encoding="utf-8") as f:
    f.write(f"Pages: {len(pdf.pages)}\n")
    f.write(f"Page size: {p.width} x {p.height}\n")
    f.write(f"Orientation: {orient}\n\n")
    
    for i, page in enumerate(pdf.pages):
        f.write(f"=== Page {i+1} ===\n")
        text = page.extract_text()
        if text:
            f.write(text + "\n\n")
        else:
            f.write("(no text)\n\n")

pdf.close()
print("Done. Output saved to test_pdf_output.txt")
