"""
Stage 3: Claude Final Review — Apply overrides from Claude-reviewed results.

This script reads the Claude review output and generates the final overrides.json.
It is meant to be run AFTER the Claude sub-agents have reviewed the questions.

Usage:
  1. Run audit_amendments_v2.py first (Stages 0-2)
  2. Claude reviews scratch/claude_review_input.json (Stage 3 review)
  3. Claude writes scratch/claude_review_output.json
  4. Run this script to apply the results to data/overrides.json
"""

import json
import os
import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

ROOT = r"g:\User\Downloads\TS\Code\Irrigation_Quiz"
REVIEW_OUTPUT = os.path.join(ROOT, "scratch", "claude_review_output.json")
OVERRIDES_FILE = os.path.join(ROOT, "data", "overrides.json")
MERGED_QUESTIONS = os.path.join(ROOT, "scratch", "merged_traffic_law_questions.json")

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Load review output
review = load_json(REVIEW_OUTPUT)

# Load questions for repeat detection
questions = load_json(MERGED_QUESTIONS)

# Build repeat map
def normalize_stem(text):
    return re.sub(r"[^\w一-龥]", "", text).strip().lower()

from collections import defaultdict
grouped = defaultdict(list)
for q in questions:
    norm = normalize_stem(q["question"])
    grouped[norm].append(q)

repeats_map = {}
for norm, qlist in grouped.items():
    if len(norm) < 10 or norm in ("下列敘述何者正確", "下列何者正確", "下列何者為非", "下列敘述何者錯誤"):
        continue
    bank_names = sorted(set(q["_bank_name"] for q in qlist))
    if len(bank_names) > 1:
        for q in qlist:
            repeats_map[(q["_bank_file"], str(q["id"]))] = bank_names

# Build overrides
overrides = {}

# Apply Claude-reviewed warnings
for item in review.get("confirmed_affected", []):
    bank_file = item["bank_file"]
    qid = str(item["question_id"])
    patch = {}
    if "warning" in item:
        patch["warning"] = item["warning"]
    if item.get("freeScore"):
        patch["freeScore"] = True
    if patch:
        overrides.setdefault(bank_file, {}).setdefault(qid, {}).update(patch)

# Apply repeats (independent of amendments)
for (filepath, qid), bank_names in repeats_map.items():
    overrides.setdefault(filepath, {}).setdefault(qid, {})["repeats"] = bank_names

# Write output
save_json(OVERRIDES_FILE, overrides)

total_warnings = sum(1 for bank in overrides.values() for q in bank.values() if "warning" in q)
total_free = sum(1 for bank in overrides.values() for q in bank.values() if q.get("freeScore"))
total_entries = sum(len(v) for v in overrides.values())

print(f"Overrides written to {OVERRIDES_FILE}")
print(f"  Total entries: {total_entries}")
print(f"  With warnings: {total_warnings}")
print(f"  Free score: {total_free}")
print(f"  Banks: {len(overrides)}")
