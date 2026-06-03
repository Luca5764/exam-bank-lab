import json
import os
import re
import sys
import math
import requests

# Ensure UTF-8 output on Windows terminal
sys.stdout.reconfigure(encoding='utf-8')

root_dir = r"g:\User\Downloads\TS\Code\Irrigation_Quiz"
amendments_file = os.path.join(root_dir, "data", "traffic_law_amendments.json")
merged_file = os.path.join(root_dir, "scratch", "merged_traffic_law_questions.json")
overrides_file = os.path.join(root_dir, "data", "overrides.json")
cache_file = os.path.join(root_dir, "scratch", "llm_audit_cache.json")
audit_log_file = os.path.join(root_dir, "scratch", "nlp_mapping_audit.txt")

LLM_URL = "http://127.0.0.1:1234/v1/chat/completions"
# Using Gemma since it returns direct answers without verbose reasoning token limits
LLM_MODEL = "gemma-4-26b-a4b-it-apex"

if not os.path.exists(amendments_file) or not os.path.exists(merged_file):
    print("Required data files not found!")
    sys.exit(1)

with open(amendments_file, "r", encoding="utf-8") as f:
    amendments = json.load(f)

with open(merged_file, "r", encoding="utf-8") as f:
    questions = json.load(f)

# Load LLM cache
llm_cache = {}
if os.path.exists(cache_file):
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            llm_cache = json.load(f)
        # Clear any failed/error cache entries so they can be re-run
        keys_to_delete = [
            k for k, v in llm_cache.items() 
            if "API Error" in v.get("reason", "") or "Failed to parse" in v.get("reason", "")
        ]
        for k in keys_to_delete:
            del llm_cache[k]
        print(f"Loaded cache, cleared {len(keys_to_delete)} error entries.")
    except Exception as e:
        print("Warning: Failed to load LLM cache, starting fresh.", e)

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
        "ngrams": get_ngrams(doc_text),
        "raw_text": a["text"],
        "raw_reason": a["reason"]
    })

df = {}
for doc in corpus:
    unique_tokens = set(doc["ngrams"])
    for token in unique_tokens:
        df[token] = df.get(token, 0) + 1

N = len(corpus)
idf = {}
for token, count in df.items():
    idf[token] = math.log((N + 1) / (count + 0.5)) + 1

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
        "vector": vector,
        "raw_text": doc["raw_text"],
        "raw_reason": doc["raw_reason"]
    })

# 3. Group questions to find duplicates (repeats)
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

# 4. Warnings dictionary for major amended articles
ARTICLE_WARNINGS = {
    "7-1": "⚠️ 本題涉及民眾檢舉項目（條例第 7 條之 1）。該條文於民國 110 年及 113 年進行了兩次大幅限縮修正，已刪除人行道與黃線臨停等部分檢舉項目，請以最新修正之現行條文為準。",
    "7-2": "⚠️ 本題涉及逕行舉發（條例第 7 條之 2），該條文於 110 年 12 月配合民眾檢舉新制進行了條文調整與對應，請注意最新規定。",
    "12": "⚠️ 本題涉及牌照違規處罰（條例第 12 條），該條文於 112 年 4 月修正加重了使用吊銷/註銷牌照行駛之處罰，並增列扣繳牌照或當場沒入車輛之規定。",
    "29": "⚠️ 本題涉及車輛裝載規定（條例第 29 條）。該條文於 110 年 5 月修正，處罰額度調整為新臺幣 3,000 元以上 18,000 元以下罰鍰，並記違規紀錄與記點。",
    "31": "⚠️ 本題涉及安全帶與安全椅規定（條例第 31 條）。該條文於 110 年 11 月及 112 年 4 月修正，明定大型車乘載四歲以上乘客未繫安全帶之處罰，以及幼童安置與留置兒童處罰。",
    "33": "⚠️ 本題涉及高快速公路違規（條例第 33 條），該條文於 112 年 4 月修正提高未依規定車道行駛、違規超車或未保持安全距離等之處罰額度，請以最新規定為準。",
    "35": "⚠️ 本題涉及酒駕相關規定（條例第 35 條）。酒駕新制於 111 年及 112 年多次加重處罰，包含提高同車乘客罰鍰至 6,000 ~ 15,000 元、累犯累計年限延長至 10 年、公布姓名照片、吊扣牌照二年等。",
    "35-1": "⚠️ 本題涉及酒精鎖規定（條例第 35 條之 1），該條文於 111 年 1 月修正，大幅加重了未依規定駕駛配備車輛點火自動鎖定裝置汽車之處罰（提高至 6 萬至 12 萬元）。",
    "43": "⚠️ 本題涉及危險駕駛與嚴重超速處罰（條例第 43 條）。自民國 112 年 6 月 30 日起，『嚴重超速』定義由原本的『超過最高時速 60 公里』調降為『超過最高時速 40 公里』，並加重罰鍰及吊扣牌照期限，請注意新法規定。",
    "56": "⚠️ 本題涉及停車處罰（條例第 56 條）。該條文於 114 年 10 月修正，將併排停車第二項罰鍰由定額 2,400 元修正為 1,800 元以上 3,000 元以下，並調整交岔路口與通學區停車規定。",
    "63": "⚠️ 本題涉及違規記點與吊扣駕照制度（條例第 63 條）。記點新制於民國 112 年 6 月 30 日起全面改版，由原本的『6 個月內達 6 點吊扣 1 個月』修正為『1 年內記滿 12 點者，吊扣駕駛執照 2 個月；2 年內經吊扣 2 次再犯者吊銷』。",
    "69": "⚠️ 本題涉及慢車規定更名（條例第 69 條）。自民國 111 年 11 月 30 日起，『電動自行車』正式更名為『微型電動二輪車』，且規定須型式審驗合格、登記領牌、投保強制險並年滿 14 歲始得行駛道路。",
    "69-1": "⚠️ 本題涉及微型電動二輪車新制（條例第 69 條之 1），微型電動二輪車自民國 111 年 11 月 30 日起已強制要求登記、領牌並投保強制保險始得行駛道路，請注意最新規定。",
    "90": "⚠️ 本題涉及舉發期限（條例第 90 條）。舉發期限已於民國 109 年 12 月修正，從行為終了之日起『逾三個月』縮短為『逾二個月』不得舉發（部分涉及肇事逃逸等情形除外）。"
}

# Manual verification exclusions
EXCLUSIONS = {
    # format: (bank_file, qid_str)
}

MANUAL_CORRECTIONS = {
    "questions/交通部111-1-道路交通法規.json": {
        "11": {
            "freeScore": True,
            "warning": "⚠️ 本題已列為送分題。\n【修法原因】：道路交通管理處罰條例第 31 條之 1 修正，機車駕駛人手持使用電話罰鍰已由 1,000 元提高至 1,200 元，原選項無正確答案。"
        }
    },
    "questions/交通部111-3-道路交通法規.json": {
        "16": {
            "freeScore": True,
            "warning": "⚠️ 本題已列為送分題。\n【修法原因】：道路交通管理處罰條例第 31 條之 1 修正，機車駕駛人手持使用電話罰鍰已由 1,000 元提高至 1,200 元，原選項無正確答案。"
        }
    },
    "questions/交通部111-道路交通法規.json": {
        "9": {
            "freeScore": True,
            "warning": "⚠️ 本題已列為送分題。\n【修法原因】：道路交通管理處罰條例第 56 條之 1 修正，開啟車門未留心因而肇事罰鍰已由 1,200~3,600 元調整為 2,400~4,800 元，原選項無正確答案。"
        }
    },
    "questions/交通部112-1-道路交通法規.json": {
        "17": {
            "freeScore": True,
            "warning": "⚠️ 本題已列為送分題。\n【修法原因】：行政訴訟法及行政法院組織法修正，原本由地方刑事庭管轄之簡易訴訟改由高等行政法院地方行政訴訟庭管轄，原選項無正確答案。"
        }
    },
    "questions/交通部113-1-道路交通法規.json": {
        "15": {
            "freeScore": True,
            "warning": "⚠️ 本題已列為送分題。\n【修法原因】：行政訴訟法及行政法院組織法修正，原本由地方刑事庭管轄之簡易訴訟改由高等行政法院地方行政訴訟庭管轄，原選項無正確答案。"
        }
    }
}

# Parse ROC year from bank name
def get_bank_year(bank_name):
    match = re.search(r"(\d+)", bank_name)
    if match:
        return int(match.group(1))
    return 110

def extract_json_content(text):
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match = re.search(r"({.*?})", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()

def clean_json_keys(json_str):
    json_str = re.sub(r"'\s*([a-zA-Z0-9_-]+)\s*'\s*:", r'"\1":', json_str)
    json_str = re.sub(r"([{,]\s*)([a-zA-Z0-9_-]+)\s*:", r'\1"\2":', json_str)
    json_str = re.sub(r':\s*\'(.*?)\'\s*([,}])', r': "\1"\2', json_str)
    json_str = re.sub(r",\s*}", "}", json_str)
    return json_str

def query_local_llm(q_year, q_text, options, correct_letter, correct_text, art_no, amend_date, amend_year, amend_text, amend_reason):
    amend_text_truncated = amend_text[:250] + ("..." if len(amend_text) > 250 else "")
    amend_reason_truncated = amend_reason[:100] + ("..." if len(amend_reason) > 100 else "")

    prompt = f"""分析此題是否受新修正案影響。
若修法改變了答案、廢除題目專有詞彙、或使題目不適用，請判定 is_affected = true，否則為 false。

【題目資訊】
年份：民國 {q_year} 年
題目：{q_text}
選項：
{options}
正確答案：{correct_letter} ({correct_text})

【修正案資訊】
法條：第 {art_no} 條 (民國 {amend_year} 年修正)
新條文內容：{amend_text_truncated}
修正理由：{amend_reason_truncated}

請直接回覆 JSON，不要有其他解釋：
{{
  "is_affected": true 或 false,
  "reason": "繁體中文的簡短理由"
}}
"""
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 400
    }
    try:
        r = requests.post(LLM_URL, json=payload, timeout=60)
        if r.status_code == 200:
            res_data = r.json()
            raw_content = res_data["choices"][0]["message"]["content"]
            json_str = extract_json_content(raw_content)
            json_str = clean_json_keys(json_str)
            try:
                return json.loads(json_str)
            except Exception as json_err:
                is_affected = "true" in re.search(r'"is_affected"\s*:\s*(\w+)', json_str, re.IGNORECASE).group(1).lower() if re.search(r'"is_affected"\s*:\s*(\w+)', json_str) else False
                reason_match = re.search(r'"reason"\s*:\s*"(.*?)"', json_str, re.DOTALL)
                reason = reason_match.group(1).strip() if reason_match else "Gemma non-standard format matched via regex."
                return {"is_affected": is_affected, "reason": reason}
        else:
            print(f" Error: API status {r.status_code}")
    except Exception as e:
        print(f" Error: {e}")
    return {"is_affected": False, "reason": "Failed to parse model output"}

# 5. Pipeline execution (Strategy B: Match against any newer amendment)
import threading
import concurrent.futures

cache_lock = threading.Lock()
candidates = []

for q in questions:
    filepath = q["_bank_file"]
    qid_str = str(q["id"])
    
    if (filepath, qid_str) in EXCLUSIONS:
        continue
        
    q_text = f"{q['question']} {' '.join(q['options'])}"
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
            
    # Calculate similarity with all newer amendments
    newer_scores = []
    for doc in doc_vectors:
        try:
            amend_year = int(doc["date_roc"].split('/')[0])
            if amend_year > q_year:
                similarity = 0.0
                for token, w in q_vector.items():
                    if token in doc["vector"]:
                        similarity += w * doc["vector"][token]
                newer_scores.append((similarity, doc["article_no"], doc["date_roc"], doc["raw_text"], doc["raw_reason"], amend_year))
        except Exception as e:
            pass
            
    if newer_scores:
        newer_scores.sort(key=lambda x: x[0], reverse=True)
        top_score, top_art, top_date, top_text, top_reason, amend_year = newer_scores[0]
        
        # Lower similarity threshold to 0.15 to ensure short questions matching long articles are captured
        if top_score > 0.15:
            candidates.append({
                "bank_file": filepath,
                "bank_name": q["_bank_name"],
                "id": qid_str,
                "question": q["question"],
                "options": q["options"],
                "correct_idx": q["answer"],
                "article_no": top_art,
                "date_roc": top_date,
                "amend_year": amend_year,
                "amend_text": top_text,
                "amend_reason": top_reason,
                "q_year": q_year,
                "score": top_score
            })

print(f"Total candidate questions matching similarity (funnel entrance): {len(candidates)}")

# Thread-safe LLM query helper
def process_candidate(idx, c):
    cache_key = f"{c['bank_file']}::{c['id']}"
    
    with cache_lock:
        in_cache = cache_key in llm_cache
        if in_cache:
            decision = llm_cache[cache_key]
            
    if in_cache:
        print(f"[{idx+1}/{len(candidates)}] Cache Hit for ID {c['id']} ({c['bank_name']})")
    else:
        print(f"[{idx+1}/{len(candidates)}] Querying LLM (Gemma) for ID {c['id']} of {c['bank_name']}...")
        options_text = "\n".join([f"({chr(65+i)}) {opt}" for i, opt in enumerate(c["options"])])
        
        # Support multi-answer letters and text
        if isinstance(c["correct_idx"], list):
            correct_letter = ",".join([chr(65 + idx) for idx in c["correct_idx"]])
            correct_text = ",".join([c["options"][idx] for idx in c["correct_idx"]])
        else:
            correct_letter = chr(65 + c["correct_idx"])
            correct_text = c["options"][c["correct_idx"]]
        
        decision = query_local_llm(
            q_year=c["q_year"],
            q_text=c["question"],
            options=options_text,
            correct_letter=correct_letter,
            correct_text=correct_text,
            art_no=c["article_no"],
            amend_date=c["date_roc"],
            amend_year=c["amend_year"],
            amend_text=c["amend_text"],
            amend_reason=c["amend_reason"]
        )
        
        with cache_lock:
            llm_cache[cache_key] = decision
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(llm_cache, f, ensure_ascii=False, indent=2)
                
    return c, decision

overrides = {}
audit_report = []
total_affected = 0

# Run LLM validation in parallel (5 threads)
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    futures = [executor.submit(process_candidate, i, c) for i, c in enumerate(candidates)]
    for f in concurrent.futures.as_completed(futures):
        c, decision = f.result()
        is_affected = decision.get("is_affected", False)
        reason = decision.get("reason", "")
        
        audit_report.append({
            "bank_file": c["bank_file"],
            "bank_name": c["bank_name"],
            "id": c["id"],
            "question": c["question"],
            "article_no": c["article_no"],
            "score": c["score"],
            "is_affected": is_affected,
            "reason": reason
        })
        
        if is_affected:
            total_affected += 1
            warning_msg = ARTICLE_WARNINGS.get(c["article_no"], f"⚠️ 本題涉及的條例第 {c['article_no']} 條在您考卷的年份之後曾經進行過法律修正。")
            custom_warning = f"{warning_msg}\n【地端模型分析影響原因】：{reason}"
            overrides.setdefault(c["bank_file"], {}).setdefault(c["id"], {})["warning"] = custom_warning

# Apply repeats (independent of LLM)
for key, bank_names in repeats_map.items():
    filepath, qid_str = key
    overrides.setdefault(filepath, {}).setdefault(qid_str, {})["repeats"] = bank_names

# Apply manual corrections
for bank_file, qid_patches in MANUAL_CORRECTIONS.items():
    for qid_str, patch in qid_patches.items():
        overrides.setdefault(bank_file, {}).setdefault(qid_str, {}).update(patch)

# Write overrides to overrides.json
os.makedirs(os.path.dirname(overrides_file), exist_ok=True)
with open(overrides_file, "w", encoding="utf-8") as f:
    json.dump(overrides, f, ensure_ascii=False, indent=2)

# Sort audit report by bank name and question ID for neat output
audit_report.sort(key=lambda r: (r["bank_name"], int(r["id"])))

# Write human-readable audit log
with open(audit_log_file, "w", encoding="utf-8") as f:
    f.write("========================================================================\n")
    f.write("TRAFFIC LAW QUESTIONS MAPPING - LLM VALIDATION AUDIT LOG (WIDER FUNNEL)\n")
    f.write(f"Total Candidate Matches Checked: {len(candidates)}\n")
    f.write(f"LLM Approved Affected Questions: {total_affected}\n")
    f.write("========================================================================\n\n")
    
    for r in audit_report:
        f.write(f"[{r['bank_name']} ID {r['id']}] Matched Article: 第 {r['article_no']} 條 (Similarity Score: {r['score']:.3f})\n")
        f.write(f"  Q: {r['question']}\n")
        f.write(f"  Decision: {'⚠️ AFFECTED (標記警告)' if r['is_affected'] else '✅ NOT AFFECTED (無須警告)'}\n")
        f.write(f"  Reason: {r['reason']}\n")
        f.write("-" * 80 + "\n\n")

print(f"Success! Mapped warnings to {total_affected} outdated questions out of {len(candidates)} candidates.")
print(f"Total overrides entries in overrides.json (including repeats): {sum(len(v) for v in overrides.values())}")
print(f"Detailed audit log written to: {audit_log_file}")
