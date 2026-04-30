import json
import re
from pathlib import Path

SPECIAL_NAMES = {
    "questions": "綜合題庫",
}


def format_bank_name(stem: str) -> str:
    if stem in SPECIAL_NAMES:
        return SPECIAL_NAMES[stem]

    name = stem.strip()
    name = re.sub(r"\s*\(\d+\)$", "", name)
    name = name.replace("_", " ")
    name = re.sub(r"\s*-\s*", " - ", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"^(\d{3})(?=\S)", r"\1 ", name)
    return name


def build_index():
    base_dir = Path(__file__).resolve().parent.parent

    # Target directory for the index file
    data_dir = base_dir / 'data'
    data_dir.mkdir(exist_ok=True)
    
    # Directory containing the JSON question banks
    q_dir = base_dir / 'questions'
    banks = []
    
    if q_dir.exists():
        # Scan for all .json files
        for f in sorted(q_dir.glob("*.json")):
            try:
                # Load the file to count questions
                with open(f, 'r', encoding='utf-8') as j:
                    data = json.load(j)
                    count = len(data) if isinstance(data, list) else 0
                
                banks.append({
                    "file": f"questions/{f.name}",
                    "name": format_bank_name(f.stem),
                    "count": count
                })
                print(f"Indexed: {f.name} ({count} questions)")
            except Exception as e:
                print(f"Error indexing {f.name}: {e}")
    
    # Save the static index file
    output_path = data_dir / "banks.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(banks, f, ensure_ascii=False, indent=2)
    
    print(f"\nStatic index created at: {output_path.resolve()}")
    print(f"Total banks indexed: {len(banks)}")

if __name__ == "__main__":
    build_index()
