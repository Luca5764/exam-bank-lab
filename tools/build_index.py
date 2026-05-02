import json
import re
from pathlib import Path

SPECIAL_NAMES = {
}

TRAILING_COPY_RE = re.compile(r"\s*\(\d+\)$")

SUBJECT_ALIASES = {
    "公文及法學緒論": "公文與法學緒論",
    "公文與法學緒論": "公文與法學緒論",
    "公文與農田水利相關法規": "公文與法學緒論",
    "法學緒論": "公文與法學緒論",
    "會計學概要": "會計學概要",
    "經濟學概要": "經濟學概要",
    "農田水利概論與相關法規": "農田水利概論與相關法規",
    "會計學與經濟學": "會計學與經濟學",
}

TVE_RE = re.compile(r"^(\d{3})統測專二-(.+)$")


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


def parse_bank_parts(stem: str, year_map: dict[str, str]) -> dict[str, str]:
    cleaned = TRAILING_COPY_RE.sub("", stem.strip())
    tve_match = TVE_RE.match(cleaned)
    if tve_match:
        year, subject = tve_match.groups()
        normalized_subject = SUBJECT_ALIASES.get(subject, subject)
        return {
            "year": year,
            "source": "統測專二",
            "category": "商業與管理群",
            "subject": normalized_subject,
            "originalSubject": subject,
            "displayName": f"{year} {normalized_subject}",
        }

    name = cleaned.replace("_", " ")
    name = re.sub(r"\s*-\s*", " - ", name)
    name = re.sub(r"\s+", " ", name).strip()

    year = year_map.get(cleaned)
    if not year:
        match = re.match(r"^(\d{3})(?:\s+|(?=\S))(.+)$", name)
        if match:
            year = match.group(1)
            name = match.group(2)

    if year and name.startswith(year):
        name = re.sub(rf"^{re.escape(year)}\s*", "", name).strip()

    parts = [p.strip() for p in name.split(" - ") if p.strip()]
    original_subject = parts[-1] if parts else name
    subject = SUBJECT_ALIASES.get(original_subject, original_subject)
    category = " / ".join(parts[:-1]) if len(parts) > 1 else ""
    source = "農田水利署" if year and int(year) >= 113 else "農田水利"
    if source == "農田水利署" and category == "農田水利署":
        category = "共同科目" if subject == "公文與法學緒論" else "專業科目"

    return {
        "year": year or "",
        "source": source,
        "category": category,
        "subject": subject,
        "originalSubject": original_subject,
        "displayName": f"{year} {subject}".strip(),
    }


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
                
                meta = parse_bank_parts(f.stem, year_map)
                name_context = meta["source"] if meta["source"] in ("統測專二", "農田水利署") else meta["category"]
                banks.append({
                    "file": f"questions/{f.name}",
                    "name": f"{meta['displayName']}（{name_context}）" if name_context else meta["displayName"],
                    "displayName": meta["displayName"],
                    "year": meta["year"],
                    "source": meta["source"],
                    "category": meta["category"],
                    "subject": meta["subject"],
                    "originalSubject": meta["originalSubject"],
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
