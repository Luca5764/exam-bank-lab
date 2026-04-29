import json, sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
qdir = Path(r'G:\User\Downloads\TS\Code\Irrigation_Quiz\questions')

total_all = 0
for f in sorted(qdir.glob('*.json')):
    data = json.loads(f.read_text(encoding='utf-8'))
    if not isinstance(data, list):
        print(f"{f.name}: not a list")
        continue
    n = len(data)
    total_all += n
    has_opts = sum(1 for q in data if q.get('options') and len(q['options']) >= 3)
    has_answer = sum(1 for q in data if 'answer' in q and isinstance(q['answer'], int))
    no_shuf = sum(1 for q in data if q.get('noShuffle'))
    
    print(f"\n{'='*50}")
    print(f"FILE: {f.name}")
    print(f"  Total: {n} | Valid options: {has_opts} | Has answer: {has_answer} | noShuffle: {no_shuf}")
    
    # Check for issues
    issues = []
    for q in data:
        qid = q.get('id', '?')
        opts = q.get('options', [])
        ans = q.get('answer', -1)
        if len(opts) < 2:
            issues.append(f"Q{qid}: only {len(opts)} options")
        if ans < 0 or ans >= len(opts):
            issues.append(f"Q{qid}: answer={ans} out of range (options={len(opts)})")
    
    if issues:
        print(f"  ISSUES ({len(issues)}):")
        for iss in issues[:5]:
            print(f"    - {iss}")
    else:
        print("  No issues found!")
    
    # Show first 2
    print("  Sample questions:")
    for q in data[:2]:
        qid = q.get('id', '?')
        qtxt = q.get('question', '')[:70]
        ans = q.get('answer', '?')
        opts_count = len(q.get('options', []))
        print(f"    Q{qid}: {qtxt}...")
        print(f"      -> {opts_count} options, answer={ans}")

print(f"\n{'='*50}")
print(f"GRAND TOTAL: {total_all} questions across {len(list(qdir.glob('*.json')))} files")
