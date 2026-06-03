import json
import os
import re
import sys

root_dir = r"g:\User\Downloads\TS\Code\Irrigation_Quiz"
amendments_file = os.path.join(root_dir, "data", "traffic_law_amendments.json")
merged_file = os.path.join(root_dir, "scratch", "merged_traffic_law_questions.json")

# Set output encoding to UTF-8
sys.stdout.reconfigure(encoding='utf-8')

if not os.path.exists(amendments_file) or not os.path.exists(merged_file):
    print("Required data files not found!")
    sys.exit(1)

with open(amendments_file, "r", encoding="utf-8") as f:
    amendments = json.load(f)

with open(merged_file, "r", encoding="utf-8") as f:
    questions = json.load(f)

print(f"Loaded {len(amendments)} amendments and {len(questions)} questions.")

# Group amendments by article_no
amend_by_article = {}
for a in amendments:
    art = a["article_no"]
    if art:
        amend_by_article.setdefault(art, []).append(a)

# Normalize question text
def normalize_text(text):
    text = re.sub(r"[^\w\u4e00-\u9fa5]", "", text)
    return text.strip().lower()

# Map questions to articles
# Keyword mapping for major articles
KEYWORDS_MAP = {
    "7-1": ["檢舉", "民眾檢舉"],
    "7-2": ["逕行舉發", "科學儀器", "測速"],
    "18-1": ["行車紀錄器", "行車視野", "防止捲入裝置", "行車紀錄"],
    "29": ["裝載", "整體物品", "牽引拖架", "附掛拖車"],
    "31": ["安全帶", "安全椅", "幼童", "兒童", "留置於車內", "安全帽", "繫安全帶"],
    "31-1": ["行動電話", "手持方式", "有礙駕駛安全"],
    "32-1": ["非屬汽車", "動力載具", "動力運動", "動力器具"],
    "35": ["酒精", "酒測", "同車乘客", "吐氣", "拒絕接受", "吸食毒品", "酒駕", "酒精濃度"],
    "35-1": ["點火自動鎖定", "自動鎖定裝置", "車輛點火自動鎖定"],
    "56": ["併排停車", "身心障礙專用", "停車處所", "通學區"],
    "56-1": ["開關車門"],
    "69": ["慢車", "自行車", "個人行動器具", "電動輔助自行車", "微型電動二輪車"],
    "69-1": ["型式審驗合格標章", "懸掛牌照", "強制汽車責任保險"],
    "85-1": ["連續舉發", "隔二小時", "相距六公里", "相隔六分鐘"]
}

# Group questions by normalized stem
grouped_questions = {}
for q in questions:
    norm = normalize_text(q["question"])
    grouped_questions.setdefault(norm, []).append(q)

print(f"Total unique questions (normalized): {len(grouped_questions)}")

# Audit conflicts and prepare overrides list
overrides_db = {}
reports = []

# Map repeating years to each question
for norm, list_q in grouped_questions.items():
    # Collect repeating bank names
    repeats_info = [q["_bank_name"] for q in list_q]
    
    # Identify which articles might match
    matched_articles = []
    question_text = list_q[0]["question"]
    
    # Explicit article mention matching (e.g. 第三十一條)
    # We check common article names
    cn_numbers = ["七", "十", "十二", "十五", "十六", "十八", "二十一", "二十二", "二十三", "二十四", "二十九", "三十", "三十一", "三十二", "三十三", "三十五", "四十三", "四十四", "四十五", "四十七", "四十八", "五十六", "六十", "六十一", "六十三", "六十五", "六十六", "六十七", "六十九", "七十一", "七十二", "七十三", "七十四", "七十八", "八十", "八十二", "八十四", "八十五", "八十六", "八十七", "九十", "九十二"]
    
    for cn in cn_numbers:
        # Match e.g. 第三十一條
        pattern = f"第\\s*{cn}\\s*條"
        if re.search(pattern, question_text):
            # Convert cn to digit
            # A simple lookup helper
            pass
            
    # Keyword concept match
    for art, kw_list in KEYWORDS_MAP.items():
        if any(kw in question_text for kw in kw_list):
            matched_articles.append(art)
            
    matched_articles = list(set(matched_articles))
    
    # Apply repeats and matched articles to each question metadata
    for q in list_q:
        q_key = (q["_bank_file"], q["id"])
        overrides_db.setdefault(q["_bank_file"], {}).setdefault(str(q["id"]), {
            "repeats": repeats_info,
            "matched_articles": matched_articles
        })

# Let's inspect the true answer changes in conflicting duplicate groups
conflicts_count = 0
for norm, list_q in grouped_questions.items():
    if len(list_q) > 1:
        # Get answers and options
        ans_texts = []
        for q in list_q:
            ans = q["answer"]
            opts = q["options"]
            if isinstance(ans, list):
                val = tuple(sorted([opts[i] for i in ans if i < len(opts)]))
            else:
                val = opts[ans] if ans < len(opts) else ""
            ans_texts.append(val)
            
        if len(set(ans_texts)) > 1:
            conflicts_count += 1
            reports.append({
                "question": list_q[0]["question"],
                "instances": [
                    {
                        "bank": q["_bank_name"],
                        "file": q["_bank_file"],
                        "id": q["id"],
                        "options": q["options"],
                        "answer": q["answer"],
                        "answer_text": text
                    }
                    for q, text in zip(list_q, ans_texts)
                ]
            })

print(f"Detected {conflicts_count} groups with answer/option conflicts.")

# Write audit report
report_path = os.path.join(root_dir, "scratch", "amendment_mapping_report.json")
with open(report_path, "w", encoding="utf-8") as f:
    json.dump(reports, f, ensure_ascii=False, indent=2)

print(f"Report written to {report_path}")

# Let's save a draft of overrides
overrides_path = os.path.join(root_dir, "data", "overrides.json")
# We only write the final structured overrides to overrides.json
# We'll write a script to fill actual overrides based on our findings
with open(overrides_path, "w", encoding="utf-8") as f:
    json.dump(overrides_db, f, ensure_ascii=False, indent=2)
print(f"Draft overrides written to {overrides_path}")
