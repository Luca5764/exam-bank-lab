"""
Stage 3 Runner: Reads claude_review_input.json and prepares structured batches
for Claude sub-agent review.

This script formats the data for review. The actual review is done by Claude
via the CLI (sub-agents process each batch).

Output: scratch/claude_review_output.json
"""

import json
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')

ROOT = r"g:\User\Downloads\TS\Code\Irrigation_Quiz"
INPUT_FILE  = os.path.join(ROOT, "scratch", "claude_review_input.json")
OUTPUT_FILE = os.path.join(ROOT, "scratch", "claude_review_output.json")

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

data = load_json(INPUT_FILE)
meta = data["metadata"]
batch_a = data["batch_a_review"]
batch_b = data["batch_b_qa_sample"]

print(f"Stage 3 Review Input Loaded")
print(f"  Batch A (flagged): {len(batch_a)} questions")
print(f"  Batch B (QA sample): {len(batch_b)} questions")
print(f"  Total for review: {len(batch_a) + len(batch_b)}")

# Format each question for review
def format_for_review(item, batch_label):
    """Format a single question into a review prompt block."""
    q = item
    d = q["llm_decision"]

    options_str = "\n".join(
        f"  ({chr(65+i)}) {opt}" for i, opt in enumerate(q["options"])
    )

    if isinstance(q["correct_idx"], list):
        correct = ", ".join(f"({chr(65+i)})" for i in q["correct_idx"])
    else:
        correct = f"({chr(65 + q['correct_idx'])})"

    amendments_str = ""
    for a in q["matched_amendments"]:
        amendments_str += f"\n  [{a['law_name']}] 第 {a['article_no']} 條（修正日期：{a['latest_date']}）\n"
        amendments_str += f"  信號：{', '.join(a['signals'])}\n"
        amendments_str += f"  條文：{a['text'][:400]}\n"
        if a.get("reason"):
            amendments_str += f"  理由：{a['reason'][:200]}\n"

    return {
        "batch": batch_label,
        "bank_file": q["bank_file"],
        "bank_name": q["bank_name"],
        "question_id": q["question_id"],
        "q_year": q["q_year"],
        "question": q["question"],
        "options": options_str,
        "correct_answer": correct,
        "gemma_decision": {
            "is_affected": d["is_affected"],
            "confidence": d.get("confidence", 0),
            "reason": d["reason"],
            "affected_article": d.get("affected_article"),
        },
        "amendments": amendments_str,
    }

review_items = []
for item in batch_a:
    review_items.append(format_for_review(item, "A"))
for item in batch_b:
    review_items.append(format_for_review(item, "B"))

# Write formatted review file
formatted_file = os.path.join(ROOT, "scratch", "claude_review_formatted.json")
with open(formatted_file, "w", encoding="utf-8") as f:
    json.dump(review_items, f, ensure_ascii=False, indent=2)

print(f"\nFormatted review items written to: {formatted_file}")
print(f"\nTo run Stage 3, use Claude CLI or sub-agents to process each item.")
print(f"Expected output format in {OUTPUT_FILE}:")
print("""
{
  "confirmed_affected": [
    {
      "bank_file": "questions/...",
      "question_id": "9",
      "warning": "⚠️ ...",
      "freeScore": false,
      "affected_article": "第45條",
      "review_note": "..."
    }
  ],
  "confirmed_safe": [
    {
      "bank_file": "questions/...",
      "question_id": "5",
      "review_note": "..."
    }
  ],
  "qa_issues": [
    {
      "bank_file": "questions/...",
      "question_id": "12",
      "issue": "Gemma missed this - actually affected",
      "warning": "⚠️ ...",
      "freeScore": false
    }
  ]
}
""")
