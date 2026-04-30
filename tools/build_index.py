import json
import re
from pathlib import Path

SPECIAL_NAMES = {
}

TRAILING_COPY_RE = re.compile(r"\s*\(\d+\)$")


def build_pdf_year_map(pdf_root: Path) -> dict[str, str]:
    year_map = {}
    if not pdf_root.exists():
        return year_map

    for pdf in pdf_root.rglob("*.pdf"):
        year = pdf.parent.name.strip()
        year_map[pdf.stem] = year
    return year_map


def format_bank_name(stem: str, year_map: dict[str, str]) -> str:
    if stem in SPECIAL_NAMES:
        return SPECIAL_NAMES[stem]

    name = stem.strip()
    name = TRAILING_COPY_RE.sub("", name)
    name = name.replace("_", " ")
    name = re.sub(r"\s*-\s*", " - ", name)
    name = re.sub(r"\s+", " ", name).strip()
    year = year_map.get(stem)
    if year and not re.match(rf"^{re.escape(year)}(?:\b|(?=\S))", name):
        name = f"{year} {name}"
    name = re.sub(r"^(\d{3})(?=\S)", r"\1 ", name)

    match = re.match(r"^(\d{3})\s+(.+)$", name)
    if not match:
        return name

    year_text, rest = match.groups()
    parts = [p.strip() for p in rest.split(" - ") if p.strip()]
    if len(parts) <= 1:
        return name

    subject = parts[-1]
    context = " / ".join(parts[:-1])
    return f"{year_text} {subject}（{context}）"


def extract_year(stem: str, year_map: dict[str, str]) -> int:
    year = year_map.get(stem)
    if not year:
        match = re.match(r"^(\d{3})\b", stem.replace("_", " "))
        if match:
            year = match.group(1)
    return int(year) if year and year.isdigit() else 999


def bank_sort_key(path: Path, year_map: dict[str, str]):
    stem = path.stem
    return (extract_year(stem, year_map), format_bank_name(stem, year_map))


def build_index():
    base_dir = Path(__file__).resolve().parent.parent

    # Target directory for the index file
    data_dir = base_dir / 'data'
    data_dir.mkdir(exist_ok=True)
    
    # Directory containing the JSON question banks
    q_dir = base_dir / 'questions'
    pdf_root = base_dir / '農田水利'
    year_map = build_pdf_year_map(pdf_root)
    banks = []
    
    if q_dir.exists():
        # Scan for all .json files
        for f in sorted(q_dir.glob("*.json"), key=lambda p: bank_sort_key(p, year_map)):
            if f.stem == "questions":
                print(f"Skipped: {f.name} (legacy catch-all bank)")
                continue
            try:
                # Load the file to count questions
                with open(f, 'r', encoding='utf-8') as j:
                    data = json.load(j)
                    count = len(data) if isinstance(data, list) else 0
                
                banks.append({
                    "file": f"questions/{f.name}",
                    "name": format_bank_name(f.stem, year_map),
                    "count": count
                })
                print(f"Indexed: {f.name} ({count} questions)")
            except Exception as e:
                print(f"Error indexing {f.name}: {e}")
    
    # Save the static index file
    output_path = data_dir / "banks.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(banks, f, ensure_ascii=False, indent=2)
        f.write("\n")
    
    print(f"\nStatic index created at: {output_path.resolve()}")
    print(f"Total banks indexed: {len(banks)}")

if __name__ == "__main__":
    build_index()
