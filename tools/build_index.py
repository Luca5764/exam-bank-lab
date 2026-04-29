import json
from pathlib import Path

def build_index():
    # Target directory for the index file
    data_dir = Path('../data')
    data_dir.mkdir(exist_ok=True)
    
    # Directory containing the JSON question banks
    q_dir = Path('../questions')
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
                    "name": f.stem,
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
