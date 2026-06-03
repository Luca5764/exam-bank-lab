import json
import os
import re
import sys
import math

root_dir = r"g:\User\Downloads\TS\Code\Irrigation_Quiz"
amendments_file = os.path.join(root_dir, "data", "traffic_law_amendments.json")
merged_file = os.path.join(root_dir, "scratch", "merged_traffic_law_questions.json")
overrides_file = os.path.join(root_dir, "data", "overrides.json")

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

if not os.path.exists(amendments_file) or not os.path.exists(merged_file):
    print("Required data files not found!")
    sys.exit(1)

with open(amendments_file, "r", encoding="utf-8") as f:
    amendments = json.load(f)

with open(merged_file, "r", encoding="utf-8") as f:
    questions = json.load(f)

print(f"Loaded {len(amendments)} amendments and {len(questions)} questions.")

# 1. Chinese text tokenizer (character unigrams + bigrams)
def get_ngrams(text):
    text = re.sub(r"[^\w\u4e00-\u9fa5]", "", text)
    tokens = []
    tokens.extend(list(text))
    for i in range(len(text) - 1):
        tokens.append(text[i:i+2])
    return tokens

# 2. Build TF-IDF for the 83 amendments
corpus = []
for idx, a in enumerate(amendments):
    doc_text = f"{a['article_raw']} {a['text']} {a['reason']}"
    corpus.append({
        "index": idx,
        "article_no": a["article_no"],
        "date_roc": a["date_roc"],
        "text": doc_text,
        "ngrams": get_ngrams(doc_text)
    })

# Compute Document Frequency (DF)
df = {}
for doc in corpus:
    unique_tokens = set(doc["ngrams"])
    for token in unique_tokens:
        df[token] = df.get(token, 0) + 1

N = len(corpus)
idf = {}
for token, count in df.items():
    idf[token] = math.log((N + 1) / (count + 0.5)) + 1

# Compute TF-IDF vectors for documents
doc_vectors = []
for doc in corpus:
    tf = {}
    for token in doc["ngrams"]:
        tf[token] = tf.get(token, 0) + 1
    
    vector = {}
    length_sq = 0.0
    for token, val in tf.items():
        w = val * idf.get(token, 0.0)
        vector[token] = w
        length_sq += w * w
    length = math.sqrt(length_sq)
    
    if length > 0:
        for token in vector:
            vector[token] /= length
            
    doc_vectors.append({
        "article_no": doc["article_no"],
        "date_roc": doc["date_roc"],
        "vector": vector
    })

# 3. Group questions to find duplicates
def normalize_stem(text):
    text = re.sub(r"[^\w\u4e00-\u9fa5]", "", text)
    return text.strip().lower()

grouped = {}
for q in questions:
    norm = normalize_stem(q["question"])
    grouped.setdefault(norm, []).append(q)

repeats_map = {}
for norm, list_q in grouped.items():
    if len(norm) < 10 or norm in ["下列敘述何者正確", "下列何者正確", "下列何者為非", "下列敘述何者錯誤"]:
        continue
    bank_names = sorted(list(set(q["_bank_name"] for q in list_q)))
    if len(bank_names) > 1:
        for q in list_q:
            key = (q["_bank_file"], str(q["id"]))
            repeats_map[key] = bank_names

# 4. Article Warnings Dictionary
ARTICLE_WARNINGS = {
    "7-1": "⚠️ 本題涉及民眾檢舉項目（條例第 7 條之 1）。該條文於民國 110 年及 113 年進行了兩次大幅限縮修正，已刪除人行道與黃線臨停等部分檢舉項目，請以最新修正之現行條文為準。",
    "7-2": "⚠️ 本題涉及逕行舉發（條例第 7 條之 2），該條文於 110 年 12 月配合民眾檢舉新制進行了條文調整與對應，請注意最新規定。",
    "12": "⚠️ 本題涉及牌照違規處罰（條例第 12 條），該條文於 112 年 4 月修正加重了使用吊銷/註銷牌照行駛之處罰，並增列扣繳牌照或當場沒入車輛之規定。",
    "29": "⚠️ 本題涉及車輛裝載規定（條例第 29 條）。該條文於 110 年 5 月修正，處罰額度調整為新臺幣 3,000 元以上 18,000 元以下罰鍰，並記違規紀錄與記點。",
    "31": "⚠️ 本題涉及安全帶與安全椅規定（條例第 31 條）。該條文於 110 年 11 月及 112 年 4 月修正，明定大型車乘載四歲以上乘客未繫安全帶之處罰，以及幼童安置與留置兒童處罰。",
    "35": "⚠️ 本題涉及酒駕相關規定（條例第 35 條）。酒駕新制於 111 年及 112 年多次加重處罰，包含提高同車乘客罰鍰至 6,000 ~ 15,000 元、累犯累計年限延長至 10 年、公布姓名照片、吊扣牌照二年等。",
    "35-1": "⚠️ 本題涉及酒精鎖規定（條例第 35 條之 1），該條文於 111 年 1 月修正，大幅加重了未依規定駕駛配備車輛點火自動鎖定裝置汽車之處罰（提高至 6 萬至 12 萬元）。",
    "56": "⚠️ 本題涉及停車處罰（條例第 56 條）。該條文於 114 年 10 月修正，將併排停車第二項罰鍰由定額 2,400 元修正為 1,800 元以上 3,000 元以下，並調整交岔路口與通學區停車規定。",
    "63": "⚠️ 本題涉及違規記點與吊扣駕照制度（條例第 63 條）。記點新制於民國 112 年 6 月 30 日起全面改版，由原本的『6 個月內達 6 點吊扣 1 個月』修正為『1 年內記滿 12 點者，吊扣駕駛執照 2 個月；2 年內經吊扣 2 次再犯者吊銷』。",
    "69": "⚠️ 本題涉及電動自行車新規（條例第 69 條）。自民國 111 年 11 月 30 日起，『電動自行車』正式更名為『微型電動二輪車』，且規定須型式審驗合格、登記領牌、投保強制險並年滿 14 歲始得行駛道路。",
    "69-1": "⚠️ 本題涉及微型電動二輪車新制（條例第 69 條之 1），微型電動二輪車自民國 111 年 11 月 30 日起已強制要求登記、領牌並投保強制保險始得行駛道路，請注意最新規定。",
    "90": "⚠️ 本題涉及舉發期限（條例第 90 條）。舉發期限已於民國 109 年 12 月修正，從行為終了之日起『逾三個月』縮短為『逾二個月』不得舉發（部分涉及肇事逃逸等情形除外）。"
}

# Add general warning for any other amended articles
def get_general_warning(art_no, date_roc):
    return f"⚠️ 本題涉及的條例第 {art_no} 條在您考卷的年份（民國 {date_roc.split('/')[0]} 年前）之後曾經進行過法律修正。閱讀與做答時請注意最新現行法規內容。"

# 5. Overrides mapping logic
overrides = {}
mapped_warnings_count = 0

# Parse ROC year from bank name (e.g. "110 道路交通法規" -> 110)
def get_bank_year(bank_name):
    match = re.search(r"(\d+)", bank_name)
    if match:
        return int(match.group(1))
    return 110 # fallback

for q in questions:
    filepath = q["_bank_file"]
    qid_str = str(q["id"])
    q_text = f"{q['question']} {' '.join(q['options'])}"
    
    # Extract query year
    q_year = get_bank_year(q["_bank_name"])
    
    # Compute query TF-IDF vector
    q_ngrams = get_ngrams(q_text)
    q_tf = {}
    for token in q_ngrams:
        q_tf[token] = q_tf.get(token, 0) + 1
        
    q_vector = {}
    q_length_sq = 0.0
    for token, val in q_tf.items():
        w = val * idf.get(token, 0.0)
        q_vector[token] = w
        q_length_sq += w * w
    q_length = math.sqrt(q_length_sq)
    
    if q_length > 0:
        for token in q_vector:
            q_vector[token] /= q_length
            
    # Calculate similarity with all documents
    scores = []
    for doc in doc_vectors:
        similarity = 0.0
        for token, w in q_vector.items():
            if token in doc["vector"]:
                similarity += w * doc["vector"][token]
        scores.append((similarity, doc["article_no"], doc["date_roc"]))
        
    scores.sort(key=lambda x: x[0], reverse=True)
    top_score, top_art, top_date = scores[0]
    
    q_overrides = {}
    
    # Chronological Check: Was the matched article amended AFTER the question's year?
    # top_date is formatted as "ROC_YEAR/MM/DD", e.g. "112/04/14"
    if top_score > 0.22:
        try:
            amend_year = int(top_date.split('/')[0])
            if amend_year > q_year:
                # Question is outdated under this amendment!
                warning_msg = ARTICLE_WARNINGS.get(top_art, get_general_warning(top_art, top_date))
                q_overrides["warning"] = warning_msg
                mapped_warnings_count += 1
        except Exception as e:
            pass

    # Apply repeats if any
    key = (filepath, qid_str)
    if key in repeats_map:
        q_overrides["repeats"] = repeats_map[key]
        
    if q_overrides:
        overrides.setdefault(filepath, {})[qid_str] = q_overrides

# Write overrides to data/overrides.json
os.makedirs(os.path.dirname(overrides_file), exist_ok=True)
with open(overrides_file, "w", encoding="utf-8") as f:
    json.dump(overrides, f, ensure_ascii=False, indent=2)

print(f"Success! Mapped warnings to {mapped_warnings_count} outdated questions.")
print(f"Total overrides entries in overrides.json: {sum(len(v) for v in overrides.values())}")
