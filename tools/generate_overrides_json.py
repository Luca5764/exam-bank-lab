import json
import os
import re
import sys

root_dir = r"g:\User\Downloads\TS\Code\Irrigation_Quiz"
merged_file = os.path.join(root_dir, "scratch", "merged_traffic_law_questions.json")
overrides_file = os.path.join(root_dir, "data", "overrides.json")

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

if not os.path.exists(merged_file):
    print("Merged questions file not found!")
    sys.exit(1)

with open(merged_file, "r", encoding="utf-8") as f:
    questions = json.load(f)

# Normalize question text
def normalize_text(text):
    text = re.sub(r"[^\w\u4e00-\u9fa5]", "", text)
    return text.strip().lower()

# Group questions to find duplicates
grouped = {}
for q in questions:
    norm = normalize_text(q["question"])
    grouped.setdefault(norm, []).append(q)

# Build a map of question keys to repeating bank names
repeats_map = {}
for norm, list_q in grouped.items():
    # If the stem is too short or generic, skip repeating label
    if len(norm) < 10 or norm in ["下列敘述何者正確", "下列何者正確", "下列何者為非", "下列敘述何者錯誤"]:
        continue
    
    bank_names = sorted(list(set(q["_bank_name"] for q in list_q)))
    if len(bank_names) > 1:
        for q in list_q:
            key = (q["_bank_file"], str(q["id"]))
            repeats_map[key] = bank_names

# Specific overrides & warnings logic
overrides = {}

for q in questions:
    filepath = q["_bank_file"]
    qid_str = str(q["id"])
    qtext = q["question"]
    
    q_overrides = {}
    
    # 1. Old demerit points rule (6 points in 6 months = 1 month suspension)
    if "6" in qtext and ("點" in qtext or "個月" in qtext) and ("吊扣" in qtext or "處分" in qtext or "記點" in qtext) and ("75歲" not in qtext) and ("道路安全講習" not in qtext):
        q_overrides["warning"] = "⚠️ 本題為舊法規定（6 個月內達 6 點吊扣 1 個月）。自民國 112 年 6 月 30 日起已修正為：『汽車駕駛人於 1 年內記違規點數每達 12 點者，吊扣駕駛執照 2 個月；2 年內經吊扣駕駛執照 2 次，再違反記點規定者，吊銷其駕駛執照。』"
    
    # 2. Old demerit points repeat offense suspension window (1 year vs 2 years)
    elif "違規記點" in qtext and "1" in qtext and "吊扣" in qtext and "2次" in qtext:
        q_overrides["warning"] = "⚠️ 本題為舊法規定。自民國 112 年 6 月 30 日起已修正為：『二年內經吊扣駕駛執照二次，再違反記點規定者，吊銷其駕駛執照。』"
    
    # 3. Old speeding threshold (60 km/h severe speeding)
    elif "最高時速" in qtext and "60" in qtext and ("超速" in qtext or "牌照" in qtext or "罰鍰" in qtext):
        q_overrides["warning"] = "⚠️ 本題為舊法規定。自民國 112 年 6 月 30 日起，『嚴重超速』定義由超過最高速限 60 公里修正為超過 40 公里，且吊扣該汽車牌照期間由 3 個月延長為 6 個月，罰鍰上限亦提高至 36,000 元。"
        
    # 4. Old electric bicycle naming (電動自行車 -> 微型電動二輪車)
    elif "電動自行車" in qtext and "型式審驗" in qtext and "速率" in qtext:
        q_overrides["warning"] = "⚠️ 本題提到的『電動自行車』自民國 111 年 11 月 30 日起已正式更名為『微型電動二輪車』，且規定須登記、領用、懸掛牌照並投保強制保險始得行駛道路。"
        
    # 5. Parking hydrant warning (if any question states 20 or 25 meters, which are wrong options)
    elif "消防栓" in qtext and ("20" in qtext or "25" in qtext or "公尺" in qtext):
        q_overrides["warning"] = "⚠️ 注意：交岔路口及公共汽車招呼站 10 公尺內、消防車出入口 5 公尺內、消防栓前 10 公尺內，均不得停車或臨時停車。選項中的 20 公尺或 25 公尺為錯誤干擾項。"
        
    # Apply repeats if any
    key = (filepath, qid_str)
    if key in repeats_map:
        q_overrides["repeats"] = repeats_map[key]
        
    # If we have any overrides for this question, store it
    if q_overrides:
        overrides.setdefault(filepath, {})[qid_str] = q_overrides

# Write overrides to data/overrides.json
os.makedirs(os.path.dirname(overrides_file), exist_ok=True)
with open(overrides_file, "w", encoding="utf-8") as f:
    json.dump(overrides, f, ensure_ascii=False, indent=2)

print(f"Generated overrides for {sum(len(v) for v in overrides.values())} questions across {len(overrides)} bank files.")
